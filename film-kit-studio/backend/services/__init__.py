# Film Kit Studio — Backend Services Package

from services.visual_providers import get_visual_provider, generate_visual
from services.voice_providers import synthesize_narration, get_voice_provider
from services.music_providers import generate_score, get_music_provider
from services.script_providers import generate_script, get_script_provider
from services.nim_llm import generate_script as nim_generate_script

# M1: Director Agent
from services.director import (
    DirectorPlanner,
    DirectorCritic,
    FallbackCritic,
    ContinuityTracker,
    DirectorLoop,
    NLEExporter,
    DirectorRun,
    Beat,
    SceneSpec,
    CritiqueResult,
    DirectorRunStatus,
)

# M2: Advanced Visual Control
from services.training import (
    LoRATrainingConfig,
    TrainingBackend,
    TrainingStatus,
    submit_lora_training,
    get_training_status,
    cancel_training,
    download_lora,
    DatasetCurator,
    get_model_registry,
)

from services.face_animation import (
    run_lip_sync,
)

# M3: Audio Post
from services.audio_post import (
    StemSeparator,
    LoudnessNormalizer,
    AudioConform,
    run_audio_post,
)

# Color pipeline
from services.color import (
    LUTLibrary,
    ColourlabAI,
    ResolveAPI,
    CDL,
    apply_lut,
)

# NLE Export
from utils.nle_export import (
    export_edl,
    export_fcpxml,
    export_premiere_xml,
    export_davinci_drt,
)

# Mastering
from utils.ffmpeg_ops import (
    export_prores,
    export_dnxhr,
    build_dcp_package,
    export_imf,
    write_cdl_xml,
)

# VFX Export
from utils.vfx_export import (
    export_alpha_plates,
    export_udim_layout,
)

__all__ = [
    # Original providers
    "get_visual_provider",
    "generate_visual",
    "synthesize_narration",
    "get_voice_provider",
    "generate_score",
    "get_music_provider",
    "generate_script",
    "get_script_provider",
    "nim_generate_script",

    # M1: Director
    "DirectorPlanner",
    "DirectorCritic",
    "FallbackCritic",
    "ContinuityTracker",
    "DirectorLoop",
    "NLEExporter",
    "DirectorRun",
    "Beat",
    "SceneSpec",
    "CritiqueResult",
    "DirectorRunStatus",

    # M2: Visual Control
    "LoRATrainingConfig",
    "TrainingBackend",
    "TrainingStatus",
    "submit_lora_training",
    "get_training_status",
    "cancel_training",
    "download_lora",
    "DatasetCurator",
    "get_model_registry",
    "run_lip_sync",

    # M3: Audio Post
    "StemSeparator",
    "LoudnessNormalizer",
    "AudioConform",
    "run_audio_post",

    # M3: Color
    "LUTLibrary",
    "ColourlabAI",
    "ResolveAPI",
    "CDL",
    "apply_lut",

    # M3: NLE Export
    "export_edl",
    "export_fcpxml",
    "export_premiere_xml",
    "export_davinci_drt",

    # M3: Mastering
    "export_prores",
    "export_dnxhr",
    "build_dcp",
    "export_imf",
    "write_cdl_xml",

    # M3: VFX Export
    "export_alpha_plates",
    "export_udim_layout",
]