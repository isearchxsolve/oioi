"""
Audio Post-Production — Stem separation, loudness normalization, conform.

Uses Demucs for source separation into VO/Music/SFX/Ambience stems.
EBU R128 / ATSC A/85 loudness compliance for broadcast/streaming.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class AudioPostError(Exception):
    pass


# ════════════════════════════════════════════════════════════════════════════
# STEM SEPARATION (DEMUCS)
# ════════════════════════════════════════════════════════════════════════════

class StemSeparator:
    """
    Source separation using Demucs (Hybrid Transformer).
    
    Models:
    - htdemucs: 4-stem (drums, bass, other, vocals) - default
    - htdemucs_ft: fine-tuned for music
    - mdx_extra: 6-stem (drums, bass, other, vocals, guitar, piano)
    """

    def __init__(
        self,
        model: str = "htdemucs",
        device: str = "cpu",
        shifts: int = 1,
        overlap: float = 0.25,
        segment: Optional[int] = None,
    ):
        self.model = model
        self.device = device
        self.shifts = shifts
        self.overlap = overlap
        self.segment = segment
        self._model = None

    def _load_model(self):
        """Lazy-load Demucs model."""
        if self._model is not None:
            return

        try:
            import torch
            from demucs import pretrained
            from demucs.apply import apply_model
        except ImportError:
            raise AudioPostError("demucs not installed: pip install demucs")

        logger.info(f"Loading Demucs model: {self.model} on {self.device}")
        self._model = pretrained.get_model(self.model)
        self._model.to(self.device)
        self._model.eval()

    async def separate(
        self,
        audio_path: Path,
        output_dir: Path,
        stem_names: list[str] = None,
    ) -> dict[str, Path]:
        """
        Separate audio into stems.
        
        Returns dict: stem_name -> output_path
        """
        self._load_model()

        import torch
        import torchaudio
        from demucs.apply import apply_model
        from demucs.audio import save_audio

        output_dir.mkdir(parents=True, exist_ok=True)

        # Load audio
        wav, sr = torchaudio.load(str(audio_path))
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)  # Mono to stereo
        wav = wav.to(self.device)

        # Apply model
        logger.info(f"Separating {audio_path.name} with {self.model}...")
        sources = apply_model(
            self._model,
            wav[None],
            shifts=self.shifts,
            overlap=self.overlap,
            segment=self.segment,
            progress=True,
        )[0]  # (sources, channels, samples)

        # Default 4-stem names for htdemucs
        default_stems = ["drums", "bass", "other", "vocals"]
        stem_names = stem_names or default_stems

        # Save stems
        output_paths = {}
        for i, name in enumerate(stem_names):
            if i >= sources.shape[0]:
                break
            stem_audio = sources[i].cpu()
            out_path = output_dir / f"{audio_path.stem}_{name}.wav"
            save_audio(stem_audio, str(out_path), sr)
            output_paths[name] = out_path
            logger.info(f"  Saved {name}: {out_path}")

        return output_paths

    async def separate_to_film_stems(
        self,
        audio_path: Path,
        output_dir: Path,
        mapping: dict[str, str] = None,
    ) -> dict[str, Path]:
        """
        Separate and map to film stems: VO, Music, SFX, Ambience.
        
        Mapping for htdemucs (4-stem):
        - vocals -> VO
        - other -> SFX (sound effects, Foley)
        - drums + bass -> Music (rhythm section)
        - ambient: can be derived from 'other' with filtering
        """
        raw_stems = await self.separate(audio_path, output_dir)

        mapping = mapping or {
            "VO": "vocals",
            "Music": "drums,bass",
            "SFX": "other",
            "Ambience": "other",
        }

        film_stems = {}
        for film_stem, source_stems in mapping.items():
            sources = source_stems.split(",")
            combined = None
            sr = None

            for src in sources:
                if src not in raw_stems:
                    continue
                import torchaudio
                wav, sr = torchaudio.load(str(raw_stems[src]))
                if combined is None:
                    combined = wav
                else:
                    combined = combined + wav

            if combined is not None:
                # Normalize
                combined = combined / (combined.abs().max() + 1e-8)
                out_path = output_dir / f"{audio_path.stem}_{film_stem}.wav"
                import torchaudio
                torchaudio.save(str(out_path), combined, sr)
                film_stems[film_stem] = out_path

        return film_stems


# ════════════════════════════════════════════════════════════════════════════
# LOUDNESS NORMALIZATION (EBU R128 / ATSC A/85)
# ════════════════════════════════════════════════════════════════════════════

class LoudnessNormalizer:
    """
    Loudness normalization per EBU R128 (Europe) / ATSC A/85 (US).
    
    Target levels:
    - EBU R128: -23 LUFS integrated, -1 dBTP true peak
    - ATSC A/85: -24 LKFS integrated, -2 dBTP true peak
    - Streaming (Spotify/Apple): -14 LUFS, -1 dBTP
    - Netflix: -27 LKFS (dialog-gated), -2 dBTP
    """

    def __init__(
        self,
        target_lufs: float = -23.0,      # EBU R128 default
        target_tp_db: float = -1.0,      # True peak ceiling
        standard: str = "EBU_R128",      # EBU_R128 | ATSC_A85 | STREAMING | NETFLIX
        gate_lufs: float = -70.0,        # Relative gate per EBU R128
    ):
        self.target_lufs = target_lufs
        self.target_tp_db = target_tp_db
        self.standard = standard
        self.gate_lufs = gate_lufs

    async def normalize(
        self,
        audio_path: Path,
        output_path: Path,
        progress_callback=None,
    ) -> dict[str, Any]:
        """
        Normalize audio to target loudness.
        
        Returns dict with measured and target loudness values.
        """
        import torchaudio
        import pyloudnorm as pyln

        logger.info(f"Normalizing loudness: {audio_path} -> {output_path}")

        # Load audio
        wav, sr = torchaudio.load(str(audio_path))
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        audio = wav.numpy().T  # (samples, channels)

        # Measure loudness
        meter = pyln.Meter(sr)
        integrated = meter.integrated_loudness(audio)
        lra = meter.loudness_range(audio)
        tp = self._measure_true_peak(audio)

        logger.info(f"  Measured: {integrated:.1f} LUFS, LRA: {lra:.1f} LU, TP: {tp:.1f} dBTP")

        if progress_callback:
            await progress_callback(0.3, f"Measured: {integrated:.1f} LUFS")

        # Calculate gain
        gain_db = self.target_lufs - integrated

        # Apply gain
        gain_linear = 10 ** (gain_db / 20)
        normalized = audio * gain_linear

        # Check true peak after gain
        new_tp = self._measure_true_peak(normalized)
        if new_tp > self.target_tp_db:
            # Limit to true peak ceiling
            tp_gain_db = self.target_tp_db - new_tp
            tp_gain = 10 ** (tp_gain_db / 20)
            normalized = normalized * tp_gain
            logger.info(f"  Applied true peak limiting: {tp_gain_db:.2f} dB")

        if progress_callback:
            await progress_callback(0.7, "Applied gain, writing...")

        # Write output
        import torchaudio
        out_tensor = torch.from_numpy(normalized.T).float()
        torchaudio.save(str(output_path), out_tensor, sr=48000)

        # Verify
        verify_wav, _ = torchaudio.load(str(output_path))
        verify_audio = verify_wav.numpy().T
        final_lufs = pyln.Meter(48000).integrated_loudness(verify_audio)
        final_tp = self._measure_true_peak(verify_audio)

        logger.info(f"  Final: {final_lufs:.1f} LUFS, TP: {final_tp:.1f} dBTP")

        return {
            "input_lufs": integrated,
            "input_lra": lra,
            "input_tp_db": tp,
            "target_lufs": self.target_lufs,
            "gain_applied_db": gain_db,
            "output_lufs": final_lufs,
            "output_tp_db": final_tp,
            "standard": self.standard,
        }

    def _measure_true_peak(self, audio: np.ndarray) -> float:
        """Measure true peak (4x oversampled)."""
        # Simple 4x oversampling approximation
        from scipy.signal import resample_poly
        oversampled = resample_poly(audio, 4, 1, axis=0)
        peak = np.max(np.abs(oversampled))
        return 20 * np.log10(peak + 1e-12)


# ════════════════════════════════════════════════════════════════════════════
# AUDIO CONFORM (EDL-BASED)
# ════════════════════════════════════════════════════════════════════════════

class AudioConform:
    """
    Conform stems to EDL timeline.
    
    Takes EDL + stems -> conforms to timeline with handles.
    """

    def __init__(
        self,
        handle_frames: int = 48,  # 2 seconds at 24fps
        sample_rate: int = 48000,
    ):
        self.handle_frames = handle_frames
        self.sample_rate = sample_rate

    async def conform(
        self,
        edl_path: Path,
        stems_dir: Path,
        output_dir: Path,
        stem_mapping: dict[str, str] = None,
    ) -> dict[str, Path]:
        """
        Conform stems to EDL timeline.
        
        Args:
            edl_path: Path to CMX 3600 EDL
            stems_dir: Directory with stem files (VO, Music, SFX, Ambience)
            output_dir: Output directory for conformed stems
            stem_mapping: EDL track name -> stem file mapping
        
        Returns dict: stem_name -> conformed_path
        """
        from utils.nle_export import parse_edl

        output_dir.mkdir(parents=True, exist_ok=True)

        # Parse EDL
        events = parse_edl(edl_path)

        stem_mapping = stem_mapping or {
            "VO": "VO",
            "MUSIC": "Music",
            "SFX": "SFX",
            "AMBIENCE": "Ambience",
        }

        import torchaudio
        import torch

        results = {}

        for stem_name, stem_file in stem_mapping.items():
            stem_path = Path(stem_file)
            if not stem_path.exists():
                # Try stems_dir
                stem_path = Path(stem_file)
                if not stem_path.exists():
                    logger.warning(f"Stem not found: {stem_file}")
                    continue

            # Load full stem
            wav, sr = torchaudio.load(str(stem_file))
            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)

            # Build conformed timeline
            total_duration = self._calculate_total_duration(events)
            timeline = torch.zeros(2, int(total_duration * 48000))

            for event in events:
                if event.get("track") != stem_name:
                    continue

                rec_in = event["record_in_frames"]
                rec_out = event["record_out_frames"]
                src_in = event["source_in_frames"]
                src_out = event["source_out_frames"]

                # Convert frames to samples (assuming 24fps)
                fps = 24
                rec_start = int(rec_in / fps * 48000)
                rec_end = int(rec_out / fps * 48000)
                src_start = int(src_in / fps * sr)
                src_end = int(src_out / fps * sr)

                if src_end <= wav.shape[1]:
                    segment = wav[:, src_start:src_end]
                    if segment.shape[1] > 0:
                        # Handle rate conversion if needed
                        if segment.shape[1] != (rec_end - rec_start):
                            # Resample
                            import torchaudio.functional as F
                            segment = F.resample(
                                segment, sr, 48000,
                                resample_method="sinc_interp_kaiser"
                            )
                        timeline[:, rec_start:rec_start+segment.shape[1]] += segment[:, :segment.shape[1]]

            # Save conformed stem
            out_path = Path(output_dir) / f"conformed_{Path(stem_file).stem}.wav"
            torchaudio.save(str(out_path), timeline, 48000)
            results[stem_name] = out_path

        return results

    def _calculate_total_duration(self, events: list) -> float:
        max_out = 0
        for e in events:
            max_out = max(max_out, e["record_out_frames"])
        return max_out / 24.0  # 24fps


# ════════════════════════════════════════════════════════════════════════════
# HIGH-LEVEL AUDIO POST PIPELINE
# ════════════════════════════════════════════════════════════════════════════

async def run_audio_post(
    mix_path: Path,
    edl_path: Path,
    output_dir: Path,
    target_lufs: float = -23.0,
    standard: str = "EBU_R128",
    progress_callback=None,
) -> dict[str, Any]:
    """
    Full audio post pipeline:
    1. Separate mix into stems (VO, Music, SFX, Ambience)
    2. Normalize each stem to target loudness
    3. Conform to EDL timeline
    4. Generate deliverables (stems + printmaster)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stems_dir = output_dir / "stems"
    stems_dir.mkdir(exist_ok=True)

    # 1. Separate
    if progress_callback:
        await progress_callback(0.1, "Separating stems...")

    separator = StemSeparator(model="htdemucs")
    film_stems = await separator.separate_to_film_stems(mix_path, stems_dir)

    # 2. Normalize each stem
    normalized = {}
    normalizer = LoudnessNormalizer(target_lufs=target_lufs)

    for i, (stem_name, stem_path) in enumerate(film_stems.items()):
        if progress_callback:
            await progress_callback(
                0.2 + 0.5 * i / len(film_stems),
                f"Normalizing {stem_name}..."
            )

        out_path = output_dir / f"{stem_name}_normalized.wav"
        result = await normalizer.normalize(stem_path, out_path)
        normalized[stem_name] = {"path": out_path, "loudness": result}

    # 3. Conform to EDL (if provided)
    conformed = {}
    if edl_path.exists():
        if progress_callback:
            await progress_callback(0.8, "Conforming to EDL...")

        conformer = AudioConform()
        conformed = await conformer.conform(edl_path, output_dir, output_dir / "conformed")

    # 4. Generate printmaster (stereo mix of all stems)
    if progress_callback:
        await progress_callback(0.9, "Generating printmaster...")

    printmaster_path = output_dir / "printmaster.wav"
    await _generate_printmaster(film_stems, printmaster_path)

    # Final loudness on printmaster
    pm_result = await normalizer.normalize(printmaster_path, output_dir / "printmaster_final.wav")

    return {
        "stems": {k: v["path"] for k, v in normalized.items()},
        "loudness_report": {k: v["loudness"] for k, v in normalized.items()},
        "conformed": conformed,
        "printmaster": output_dir / "printmaster_final.wav",
        "printmaster_loudness": pm_result,
    }


async def _generate_printmaster(stems: dict[str, Path], output_path: Path):
    """Sum all stems to stereo printmaster."""
    import torchaudio
    import torch

    master = None
    sr = 48000

    for stem_path in stems.values():
        wav, sr = torchaudio.load(str(stem_path))
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        if master is None:
            master = wav
        else:
            # Pad shorter
            max_len = max(master.shape[1], wav.shape[1])
            if master.shape[1] < max_len:
                master = torch.nn.functional.pad(master, (0, max_len - master.shape[1]))
            if wav.shape[1] < max_len:
                wav = torch.nn.functional.pad(wav, (0, max_len - wav.shape[1]))
            master = master + wav

    # Normalize
    master = master / (master.abs().max() + 1e-8)
    master = master * 0.9  # Headroom

    torchaudio.save(str(output_path), master, sr)