"""
NLE Exporter — Exports director runs to professional editing formats:
- CMX 3600 EDL (universal)
- Final Cut Pro XML (fcpxml)
- Adobe Premiere Pro XML
- DaVinci Resolve .drt (timeline + grades)
"""

import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from services.director.models import DirectorPlan, Beat, SceneSpec


class NLEExporter:
    """Exports a director run to multiple NLE formats."""

    def __init__(self):
        pass

    # ════════════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ════════════════════════════════════════════════════════════════════════

    async def export_all(
        self,
        project_dir: Path,
        plan: DirectorPlan,
        clips: list[dict[str, Any]],  # [{"clip_path", "audio_path", "scene_spec", "start_time", "duration"}]
        final_video: Optional[Path] = None,
        srt_path: Optional[Path] = None,
    ) -> dict[str, Path]:
        """Export all NLE formats."""
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)

        exports = {}

        # Prepare timeline data
        timeline = self._build_timeline(clips)

        # EDL (CMX 3600)
        edl_path = project_dir / "timeline.edl"
        self.export_edl(timeline, edl_path, final_video)
        exports["edl"] = edl_path

        # FCPXML
        fcpxml_path = project_dir / "timeline.fcpxml"
        self.export_fcpxml(timeline, fcpxml_path, final_video)
        exports["fcpxml"] = fcpxml_path

        # Premiere XML
        premiere_path = project_dir / "timeline.xml"
        self.export_premiere_xml(timeline, premiere_path, final_video)
        exports["premiere_xml"] = premiere_path

        # DaVinci DRT
        davinci_path = project_dir / "timeline.drt"
        self.export_davinci_drt(timeline, davinci_path, final_video, plan)
        exports["davinci_drt"] = davinci_path

        return exports

    def export_edl(
        self,
        timeline: list[dict],
        output_path: Path,
        master_clip: Optional[Path] = None,
    ) -> None:
        """
        Export CMX 3600 EDL (Event Decision List).
        Universal format supported by all NLEs.
        """
        lines = [
            "TITLE: FILM_KIT_STUDIO_TIMELINE",
            "FCM: NON-DROP FRAME",
            "",
        ]

        event_num = 1
        for item in timeline:
            # Timecodes in HH:MM:SS:FF format (30fps NON-DROP)
            src_in = self._frames_to_tc(item["source_in_frames"], 30)
            src_out = self._frames_to_tc(item["source_out_frames"], 30)
            rec_in = self._frames_to_tc(item["record_in_frames"], 30)
            rec_out = self._frames_to_tc(item["record_out_frames"], 30)

            clip_name = item["clip_name"][:32]  # EDL limit
            transition = item.get("transition", "CUT")

            lines.append(
                f"{event_num:03d}  {clip_name:<32}  V     C        "
                f"{src_in} {src_out} {rec_in} {rec_out}"
            )

            if transition == "crossfade":
                lines.append(
                    f"{event_num:03d}  {clip_name:<32}  V     D        "
                    f"{src_in} {src_out} {rec_in} {rec_out}"
                )
                # Dissolve transition in EDL
                lines.append(
                    f"* FROM CLIP NAME: {clip_name}"
                )
                lines.append(
                    f"* TRANSITION: DISSOLVE DURATION: {item.get('transition_duration_frames', 15):04d}"
                )

            event_num += 1

        output_path.write_text("\n".join(lines))
        logger.info(f"EDL exported to {output_path}")

    def export_fcpxml(
        self,
        timeline: list[dict],
        output_path: Path,
        master_clip: Optional[Path] = None,
    ) -> None:
        """
        Export Final Cut Pro XML (fcpxml 1.11).
        """
        from xml.etree.ElementTree import Element, SubElement, tostring
        from xml.dom import minidom

        # Root
        fcpxml = Element("fcpxml", version="1.11")

        # Resources
        resources = SubElement(fcpxml, "resources")

        # Format
        fmt = SubElement(resources, "format", {
            "id": "r1",
            "name": "FFVideoFormat1080p30",
            "frameDuration": "1001/30000s",
            "width": "1920",
            "height": "1080",
            "colorSpace": "1-1-1 (Rec. 709)",
        })

        # Asset clips
        for i, item in enumerate(timeline):
            asset = SubElement(resources, "asset", {
                "id": f"r{i+2}",
                "name": item["clip_name"],
                "uid": f"urn:uuid:{item.get('uuid', '')}",
                "start": f"{item['source_in_frames']}/30s",
                "duration": f"{item['duration_frames']}/30s",
                "hasVideo": "1",
                "hasAudio": "1",
                "audioChannels": "2",
                "audioRate": "48k",
            })
            if master_clip:
                SubElement(asset, "media-rep", {
                    "kind": "original-media",
                    "src": f"file://{master_clip.absolute()}",
                })

        # Library/Event/Project
        library = SubElement(fcpxml, "library", location="file://localhost/")
        event = SubElement(library, "event", name="Film Kit Studio Project")
        project = SubElement(event, "project", name="Timeline")
        sequence = SubElement(project, "sequence", format="r1", tcStart="0s", tcFormat="NDF")

        # Spine (video track)
        spine = SubElement(sequence, "spine")

        for i, item in enumerate(timeline):
            clip = SubElement(spine, "clip", {
                "name": item["clip_name"],
                "ref": f"r{i+2}",
                "offset": f"{item['record_in_frames']}/30s",
                "duration": f"{item['duration_frames']}/30s",
                "start": f"{item['source_in_frames']}/30s",
            })

            # Transition
            if item.get("transition") == "crossfade":
                SubElement(clip, "transition", {
                    "name": "Cross Dissolve",
                    "duration": f"{item.get('transition_duration_frames', 15)}/30s",
                })

        # Audio role (simplified)
        audio_role = SubElement(sequence, "audio-role", name="dialogue")

        # Pretty print
        xml_str = minidom.parseString(tostring(fcpxml)).toprettyxml(indent="  ")
        output_path.write_text(xml_str)
        logger.info(f"FCPXML exported to {output_path}")

    def export_premiere_xml(
        self,
        timeline: list[dict],
        output_path: Path,
        master_clip: Optional[Path] = None,
    ) -> None:
        """
        Export Adobe Premiere Pro compatible XML (Final Cut 7 XML variant).
        """
        from xml.etree.ElementTree import Element, SubElement, tostring
        from xml.dom import minidom

        xmeml = Element("xmeml", version="5")
        sequence = SubElement(xmeml, "sequence", id="sequence-1")

        # Basic sequence info
        SubElement(sequence, "name").text = "Film Kit Studio Timeline"
        SubElement(sequence, "duration").text = str(
            sum(item["duration_frames"] for item in timeline)
        )
        SubElement(sequence, "rate").append(self._build_rate_elem(30, 1001))

        # Video track
        video_track = SubElement(sequence, "media", {"type": "video"})
        track = SubElement(video_track, "track")

        for i, item in enumerate(timeline):
            clipitem = SubElement(track, "clipitem", id=f"clipitem-{i+1}")
            SubElement(clipitem, "name").text = item["clip_name"]
            SubElement(clipitem, "enabled").text = "TRUE"
            SubElement(clipitem, "duration").text = str(item["duration_frames"])
            SubElement(clipitem, "rate").append(self._build_rate_elem(30, 1001))
            SubElement(clipitem, "start").text = str(item["source_in_frames"])
            SubElement(clipitem, "end").text = str(item["source_out_frames"])
            SubElement(clipitem, "in").text = str(item["record_in_frames"])
            SubElement(clipitem, "out").text = str(item["record_out_frames"])

            # File reference
            file_elem = SubElement(clipitem, "file", id=f"file-{i+1}")
            SubElement(file_elem, "name").text = item["clip_name"]
            SubElement(file_elem, "pathurl").text = f"file://{Path(item['clip_path']).absolute()}"
            SubElement(file_elem, "rate").append(self._build_rate_elem(30, 1001))
            SubElement(file_elem, "duration").text = str(item["duration_frames"])
            SubElement(file_elem, "media", {"type": "video"}).append(self._build_video_format())

            # Transition
            if item.get("transition") == "crossfade":
                trans = SubElement(clipitem, "transition")
                SubElement(trans, "effect").append(self._build_cross_dissolve())
                SubElement(trans, "duration").text = str(item.get("transition_duration_frames", 15))
                SubElement(trans, "alignment").text = "center_at_cut"

        # Audio track (simplified)
        audio_track = SubElement(SubElement(SubElement(sequence, "media", {"type": "audio"}), "track"), "audio")

        xml_str = minidom.parseString(tostring(xmeml)).toprettyxml(indent="  ")
        output_path.write_text(xml_str)
        logger.info(f"Premiere XML exported to {output_path}")

    def export_davinci_drt(
        self,
        timeline: list[dict],
        output_path: Path,
        master_clip: Optional[Path] = None,
        plan: Optional[DirectorPlan] = None,
    ) -> None:
        """
        Export DaVinci Resolve .drt (DRT = DaVinci Resolve Timeline).
        Actually exports an FCPXML that Resolve imports natively,
        plus a companion .cdl for ASC CDL grades per clip.
        """
        # Resolve imports FCPXML natively, so we reuse that
        fcpxml_path = output_path.with_suffix(".fcpxml")
        self.export_fcpxml(timeline, fcpxml_path, master_clip)

        # Also export ASC CDL sidecars for each clip (for color grades)
        if plan:
            self._export_cdl_grades(timeline, plan, output_path.parent)

        # Create .drt as a simple marker file pointing to the fcpxml
        drt_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<DaVinciResolveTimeline>
  <ProjectName>Film Kit Studio</ProjectName>
  <TimelineName>Timeline</TimelineName>
  <FcpXmlPath>{fcpxml_path.name}</FcpXmlPath>
</DaVinciResolveTimeline>
"""
        output_path.write_text(drt_content)
        logger.info(f"DaVinci DRT exported to {output_path}")

    # ════════════════════════════════════════════════════════════════════════
    # TIMELINE BUILDING
    # ════════════════════════════════════════════════════════════════════════

    def _build_timeline(self, clips: list[dict[str, Any]]) -> list[dict]:
        """Convert clips to timeline items with frame-accurate timecodes."""
        timeline = []
        record_frame = 0

        for i, clip in enumerate(clips):
            scene = clip.get("scene_spec")
            if not scene:
                continue

            fps = 30  # Assume 30fps NON-DROP
            duration_frames = int(clip.get("duration", scene.duration_seconds) * fps)

            source_in = 0
            source_out = duration_frames

            item = {
                "clip_name": f"SCENE_{i+1:03d}_{scene.beat_id[:24]}",
                "clip_path": clip.get("clip_path", ""),
                "uuid": clip.get("uuid", ""),
                "source_in_frames": source_in,
                "source_out_frames": source_out,
                "record_in_frames": record_frame,
                "record_out_frames": record_frame + duration_frames,
                "duration_frames": duration_frames,
                "transition": scene.transition_out if i < len(clips) - 1 else "cut",
                "transition_duration_frames": int(
                    getattr(scene, "transition_duration", 0.5) * fps
                ) if scene.transition_out == "crossfade" else 0,
            }
            timeline.append(item)
            record_frame += duration_frames

        return timeline

    def _export_cdl_grades(
        self,
        timeline: list[dict],
        plan: DirectorPlan,
        output_dir: Path,
    ) -> None:
        """Export ASC CDL (Color Decision List) for each clip."""
        cdl_dir = output_dir / "cdl"
        cdl_dir.mkdir(exist_ok=True)

        for i, item in enumerate(timeline):
            scene = next(
                (s for s in plan.scene_specs if s.beat_id in item["clip_name"]),
                None,
            )
            if not scene:
                continue

            # Create basic CDL from scene's color_grade
            # In practice, this would be derived from actual grading
            cdl = {
                "SOPNode": {
                    "Slope": [1.0, 1.0, 1.0],
                    "Offset": [0.0, 0.0, 0.0],
                    "Power": [1.0, 1.0, 1.0],
                },
                "SatNode": {"Saturation": 1.0},
            }

            cdl_path = cdl_dir / f"{item['clip_name']}.cdl"
            import json
            cdl_path.write_text(json.dumps(cdl, indent=2))

    # ════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ════════════════════════════════════════════════════════════════════════

    def _frames_to_tc(self, frames: int, fps: int = 30) -> str:
        """Convert frame count to HH:MM:SS:FF timecode (NON-DROP)."""
        total_seconds = frames / fps
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        frame = int((total_seconds - int(total_seconds)) * fps)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}"

    def _build_rate_elem(self, timebase: int, ntsc: int):
        rate = ET.Element("rate")
        ET.SubElement(rate, "timebase").text = str(timebase)
        ET.SubElement(rate, "ntsc").text = "TRUE" if ntsc else "FALSE"
        return rate

    def _build_video_format(self):
        media = ET.Element("media")
        video = ET.SubElement(media, "video")
        ET.SubElement(video, "samplecharacteristics").append(self._build_rate_elem(30, 1001))
        ET.SubElement(video, "width").text = "1920"
        ET.SubElement(video, "height").text = "1080"
        ET.SubElement(video, "pixelaspectratio").text = "square"
        ET.SubElement(video, "fielddominance").text = "none"
        ET.SubElement(video, "colordepth").text = "24"
        return media

    def _build_cross_dissolve(self):
        effect = ET.Element("effect")
        ET.SubElement(effect, "name").text = "Cross Dissolve"
        ET.SubElement(effect, "effectid").text = "dissolve"
        ET.SubElement(effect, "effecttype").text = "dissolve"
        ET.SubElement(effect, "mediatype").text = "video"
        return effect


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def export_edl_simple(
    clips: list[dict],
    output_path: Path,
    fps: int = 30,
) -> None:
    """Quick EDL export for simple cases."""
    exporter = NLEExporter()
    timeline = []
    rec_frame = 0
    for i, clip in enumerate(clips):
        dur = int(clip.get("duration", 5) * fps)
        timeline.append({
            "clip_name": clip.get("name", f"CLIP_{i+1:03d}"),
            "clip_path": clip.get("path", ""),
            "source_in_frames": 0,
            "source_out_frames": dur,
            "record_in_frames": rec_frame,
            "record_out_frames": rec_frame + dur,
            "duration_frames": dur,
            "transition": clip.get("transition", "cut"),
        })
        rec_frame += dur
    exporter.export_edl(timeline, output_path)