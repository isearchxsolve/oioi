"""
NLE Export — EDL/FCPXML/Premiere XML/DaVinci DRT/AAF export.

Professional NLE round-trip for post-production workflows.
"""

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# EDL (CMX 3600) EXPORT
# ════════════════════════════════════════════════════════════════════════════

def frames_to_tc(frames: int, fps: float = 24.0, drop_frame: bool = False) -> str:
    """Convert frame count to HH:MM:SS:FF timecode."""
    if drop_frame:
        # Simplified drop frame calculation
        total_minutes = int(frames / (fps * 60))
        frames_in_min = int(fps * 60)
        drop_frames = total_minutes * 2 - total_minutes // 10 * 2
        frames += drop_frames
    
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    frame = int((total_seconds - int(total_seconds)) * 24)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}"


def export_edl(
    timeline: list[dict[str, Any]],
    output_path: Path,
    title: str = "Film Kit Studio Timeline",
    fps: float = 24.0,
) -> Path:
    """
    Export CMX 3600 EDL (Event Decision List).
    Universal format supported by all NLEs.
    """
    lines = [
        f"TITLE: {title}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    event_num = 1
    for item in timeline:
        # Timecodes in HH:MM:SS:FF format (30fps NON-DROP)
        src_in = frames_to_tc(item["source_in_frames"], 30)
        src_out = frames_to_tc(item["source_out_frames"], 30)
        rec_in = frames_to_tc(item["record_in_frames"], 30)
        rec_out = frames_to_tc(item["record_out_frames"], 30)

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
            lines.append(f"* FROM CLIP NAME: {clip_name}")
            lines.append(f"* TRANSITION: DISSOLVE DURATION: {item.get('transition_duration_frames', 15):04d}")

        event_num += 1

    output_path.write_text("\n".join(lines))
    logger.info(f"EDL exported to {output_path}")
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# FCPXML EXPORT (Final Cut Pro X)
# ════════════════════════════════════════════════════════════════════════════

def export_fcpxml(
    timeline: list[dict[str, Any]],
    output_path: Path,
    project_name: str = "Film Kit Studio Project",
    fps: float = 24.0,
    width: int = 1920,
    height: int = 1080,
    master_file: Path = None,
) -> Path:
    """Export Final Cut Pro XML (fcpxml 1.11)."""
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    fcpxml = Element("fcpxml", version="1.11")

    # Resources
    resources = SubElement(fcpxml, "resources")
    fmt = SubElement(resources, "format", {
        "id": "r1",
        "name": f"FFVideoFormat{width}x{height}p{int(fps)}",
        "frameDuration": f"1001/{int(fps * 1000)}s",
        "width": str(width),
        "height": str(height),
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
        if master_file:
            SubElement(asset, "media-rep", {
                "kind": "original-media",
                "src": f"file://{master_file.absolute()}",
            })

    # Library/Event/Project
    library = SubElement(fcpxml, "library", location="file://localhost/")
    event = SubElement(library, "event", name="Film Kit Studio Project")
    project = SubElement(event, "project", name=project_name)
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

        if item.get("transition") == "crossfade":
            SubElement(clip, "transition", {
                "name": "Cross Dissolve",
                "duration": f"{item.get('transition_duration_frames', 15)}/30s",
            })

    # Audio role
    SubElement(sequence, "audio-role", name="dialogue")

    # Pretty print
    xml_str = minidom.parseString(tostring(fcpxml)).toprettyxml(indent="  ")
    output_path.write_text(xml_str)
    logger.info(f"FCPXML exported to {output_path}")
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# PREMIERE PRO XML EXPORT
# ════════════════════════════════════════════════════════════════════════════

def _build_rate_elem(timebase: int, ntsc: bool) -> Element:
    rate = Element("rate")
    SubElement(rate, "timebase").text = str(timebase)
    SubElement(rate, "ntsc").text = "TRUE" if ntsc else "FALSE"
    return rate


def _build_video_format() -> Element:
    media = Element("media")
    video = SubElement(media, "video")
    sample = SubElement(video, "samplecharacteristics")
    sample.append(_build_rate_elem(30, True))
    SubElement(video, "width").text = "1920"
    SubElement(video, "height").text = "1080"
    SubElement(video, "pixelaspectratio").text = "square"
    SubElement(video, "fielddominance").text = "none"
    SubElement(video, "colordepth").text = "24"
    return media


def export_premiere_xml(
    timeline: list[dict[str, Any]],
    output_path: Path,
    project_name: str = "Film Kit Studio Timeline",
    master_file: Path = None,
) -> Path:
    """Export Adobe Premiere Pro compatible XML (Final Cut 7 XML variant)."""
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    xmeml = Element("xmeml", version="5")
    sequence = SubElement(xmeml, "sequence", id="sequence-1")

    SubElement(sequence, "name").text = project_name
    SubElement(sequence, "duration").text = str(
        sum(item["duration_frames"] for item in timeline)
    )
    sequence.append(_build_rate_elem(30, True))

    # Video track
    video_track = SubElement(SubElement(SubElement(sequence, "media", {"type": "video"}), "track"), "track")

    for i, item in enumerate(timeline):
        clipitem = SubElement(video_track, "clipitem", id=f"clipitem-{i+1}")
        SubElement(clipitem, "name").text = item["clip_name"]
        SubElement(clipitem, "enabled").text = "TRUE"
        SubElement(clipitem, "duration").text = str(item["duration_frames"])
        SubElement(clipitem, "rate").append(_build_rate_elem(30, True))
        SubElement(clipitem, "start").text = str(item["source_in_frames"])
        SubElement(clipitem, "end").text = str(item["source_out_frames"])
        SubElement(clipitem, "in").text = str(item["record_in_frames"])
        SubElement(clipitem, "out").text = str(item["record_out_frames"])

        file_elem = SubElement(clipitem, "file", id=f"file-{i+1}")
        SubElement(file_elem, "name").text = item["clip_name"]
        SubElement(file_elem, "pathurl").text = f"file://{master_file.absolute()}" if master_file else ""
        file_elem.append(_build_rate_elem(30, True))
        SubElement(file_elem, "duration").text = str(item["duration_frames"])
        file_elem.append(_build_video_format())

        # Transition
        if item.get("transition") == "crossfade":
            trans = SubElement(clipitem, "transition")
            effect = SubElement(trans, "effect")
            SubElement(effect, "name").text = "Cross Dissolve"
            SubElement(effect, "effectid").text = "dissolve"
            SubElement(effect, "effecttype").text = "dissolve"
            SubElement(effect, "mediatype").text = "video"
            SubElement(trans, "duration").text = str(item.get("transition_duration_frames", 15))
            SubElement(trans, "alignment").text = "center_at_cut"

    # Audio track (simplified)
    audio_media = SubElement(sequence, "media", {"type": "audio"})
    audio_track = SubElement(SubElement(audio_media, "track"), "audio")

    xml_str = minidom.parseString(tostring(xmeml)).toprettyxml(indent="  ")
    output_path.write_text(xml_str)
    logger.info(f"Premiere XML exported to {output_path}")
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# DAVINCI RESOLVE .DRT EXPORT
# ════════════════════════════════════════════════════════════════════════════

def export_davinci_drt(
    timeline: list[dict[str, Any]],
    output_path: Path,
    project_name: str = "Film Kit Studio",
    master_file: Path = None,
) -> Path:
    """Export DaVinci Resolve .drt (actually FCPXML wrapper for Resolve)."""
    # Resolve imports FCPXML natively
    fcpxml_path = output_path.with_suffix(".fcpxml")
    export_fcpxml(timeline, fcpxml_path, project_name)

    # Create .drt marker file
    drt_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<DaVinciResolveTimeline>
  <ProjectName>{project_name}</ProjectName>
  <TimelineName>Timeline</TimelineName>
  <FcpXmlPath>{fcpxml_path.name}</FcpXmlPath>
</DaVinciResolveTimeline>
"""
    output_path.write_text(drt_content)
    logger.info(f"DaVinci DRT exported to {output_path}")
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# EDL PARSER (for conform)
# ════════════════════════════════════════════════════════════════════════════

def parse_edl(edl_path: Path) -> list[dict[str, Any]]:
    """Parse CMX 3600 EDL file."""
    events = []
    with open(edl_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("TITLE:", "FCM:", "*")):
                continue

            parts = line.split()
            if len(parts) < 7:
                continue

            try:
                # Format: EVENT REEL TRACK TRANS SRC_IN SRC_OUT REC_IN REC_OUT
                event_num = parts[0]
                reel = parts[1]
                track = parts[2]
                trans = parts[3]
                src_in = parts[4]
                src_out = parts[5]
                rec_in = parts[6]
                rec_out = parts[7]

                events.append({
                    "event": int(event_num),
                    "reel": reel,
                    "track": track,
                    "transition": trans,
                    "source_in_frames": _tc_to_frames(src_in),
                    "source_out_frames": _tc_to_frames(src_out),
                    "record_in_frames": _tc_to_frames(rec_in),
                    "record_out_frames": _tc_to_frames(rec_out),
                })
            except (ValueError, IndexError):
                continue

    return events


def _tc_to_frames(tc: str, fps: int = 30) -> int:
    """Convert HH:MM:SS:FF to frame count."""
    try:
        h, m, s, f = map(int, tc.split(":"))
        return ((h * 3600 + m * 60 + s) * fps) + f
    except (ValueError, IndexError):
        return 0