"""
Pydantic Models for Director Agent.

Defines all data structures for beats, scene specs, critiques, and continuity state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# PLANNER MODELS
# ═══════════════════════════════════════════════════════════════════════════

class Beat(BaseModel):
    """A narrative beat in the film."""

    slug: str = Field(..., description="Unique snake_case identifier")
    type: str = Field(..., description="opening|inciting|rising|climax|falling|resolution|stinger")
    title: str = Field(..., description="Human-readable beat title")
    description: str = Field(..., description="2-3 sentences describing visual action")
    duration_seconds: float = Field(..., ge=3, le=60)
    mood: str = Field(..., description="tense|mysterious|romantic|action|contemplative|horrific|comedic|dramatic|epic|intimate")
    characters: list[str] = Field(default_factory=list)
    location: str = Field(..., description="Exact location name for continuity")
    time_of_day: str = Field(..., description="day|night|dawn|dusk|golden_hour")
    cinematography_notes: str = Field(default="")
    audio_notes: str = Field(default="")
    target_score: float = Field(default=0.85, ge=0.5, le=1.0)


class SceneSpec(BaseModel):
    """Detailed specification for a single generated scene/video clip."""

    beat_id: str = Field(..., description="Parent beat slug")
    index_in_beat: int = Field(default=0, ge=0)

    narration: str = Field(default="")
    visual_prompt: str = Field(..., min_length=10, max_length=500)

    shot_type: str = Field(default="medium", description="wide|medium|closeup|extreme_closeup|establishing")
    lens: str = Field(default="35mm")
    lighting: str = Field(default="natural")
    camera_move: str = Field(default="static", description="static|dolly|pan|tilt|crane|handheld|steadicam")
    color_grade: str = Field(default="cinematic")

    duration_seconds: float = Field(default=5.0, ge=1, le=30)

    characters: list[str] = Field(default_factory=list)
    location: str = Field(default="")
    time_of_day: str = Field(default="day")

    reference_images: list[str] = Field(default_factory=list)
    controlnet_inputs: dict[str, str] = Field(default_factory=dict)  # canny|depth|pose -> path
    lora_paths: dict[str, str] = Field(default_factory=dict)  # char_name -> path

    audio_cues: list[str] = Field(default_factory=list)
    transition_in: str = Field(default="cut")
    transition_out: str = Field(default="cut")


class ContinuitySetup(BaseModel):
    """Continuity bible from planner."""

    characters: list[dict[str, Any]] = Field(default_factory=list)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    global_lighting_mood: str = "cinematic"
    color_palette: list[str] = Field(default_factory=list)


class DirectorPlan(BaseModel):
    """Complete plan output from planner."""

    beats: list[Beat] = Field(default_factory=list)
    scene_specs: list[SceneSpec] = Field(default_factory=list)
    continuity_setup: ContinuitySetup = Field(default_factory=ContinuitySetup)

    estimated_total_duration: float = Field(default=60.0)
    target_genre: str = Field(default="drama")


# ═══════════════════════════════════════════════════════════════════════════
# CONTINUITY STATE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CharacterAppearance:
    """Tracked character appearance across scenes."""

    name: str
    description: str = ""
    reference_image_path: Optional[str] = None
    lora_path: Optional[str] = None
    wardrobe: dict[str, str] = field(default_factory=dict)  # scene_slug -> outfit
    props: dict[str, list[str]] = field(default_factory=dict)  # scene_slug -> [props]
    last_seen_scene: int = -1
    consistency_score: float = 1.0  # Updated by critic

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "reference_image_path": self.reference_image_path,
            "lora_path": self.lora_path,
            "wardrobe": self.wardrobe,
            "props": self.props,
            "last_seen_scene": self.last_seen_scene,
            "consistency_score": self.consistency_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterAppearance":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            reference_image_path=data.get("reference_image_path"),
            lora_path=data.get("lora_path"),
            wardrobe=data.get("wardrobe", {}),
            props=data.get("props", {}),
            last_seen_scene=data.get("last_seen_scene", -1),
            consistency_score=data.get("consistency_score", 1.0),
        )


@dataclass
class LocationProfile:
    """Tracked location state across scenes."""

    name: str
    description: str = ""
    reference_image_path: Optional[str] = None
    time_of_day: str = "day"
    lighting_setup: str = "natural"
    weather: str = "clear"
    key_features: list[str] = field(default_factory=list)
    last_used_scene: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "reference_image_path": self.reference_image_path,
            "time_of_day": self.time_of_day,
            "lighting_setup": self.lighting_setup,
            "weather": self.weather,
            "key_features": self.key_features,
            "last_used_scene": self.last_used_scene,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocationProfile":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            reference_image_path=data.get("reference_image_path"),
            time_of_day=data.get("time_of_day", "day"),
            lighting_setup=data.get("lighting_setup", "natural"),
            weather=data.get("weather", "clear"),
            key_features=data.get("key_features", []),
            last_used_scene=data.get("last_used_scene", -1),
        )


@dataclass
class ContinuityState:
    """Complete continuity state for a director run."""

    characters: dict[str, CharacterAppearance] = field(default_factory=dict)
    locations: dict[str, LocationProfile] = field(default_factory=dict)
    global_lighting_mood: str = "cinematic"
    color_palette: list[str] = field(default_factory=list)
    props_inventory: dict[str, list[str]] = field(default_factory=dict)

    def get_character(self, name: str) -> CharacterAppearance:
        if name not in self.characters:
            self.characters[name] = CharacterAppearance(name=name, description="")
        return self.characters[name]

    def get_location(self, name: str) -> LocationProfile:
        if name not in self.locations:
            self.locations[name] = LocationProfile(name=name, description="")
        return self.locations[name]

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": {k: v.to_dict() for k, v in self.characters.items()},
            "locations": {k: v.to_dict() for k, v in self.locations.items()},
            "global_lighting_mood": self.global_lighting_mood,
            "color_palette": self.color_palette,
            "props_inventory": self.props_inventory,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuityState":
        state = cls()
        state.characters = {k: CharacterAppearance.from_dict(v) for k, v in data.get("characters", {}).items()}
        state.locations = {k: LocationProfile.from_dict(v) for k, v in data.get("locations", {}).items()}
        state.global_lighting_mood = data.get("global_lighting_mood", "cinematic")
        state.color_palette = data.get("color_palette", [])
        state.props_inventory = data.get("props_inventory", {})
        return state


# ═══════════════════════════════════════════════════════════════════════════
# CRITIQUE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class CritiqueIssue(BaseModel):
    """Single issue found during critique."""

    type: str = Field(..., description="continuity|performance|technical|pacing|cinematography|audio")
    severity: str = Field(..., description="critical|major|minor|suggestion")
    description: str = Field(..., min_length=10)
    fix_suggestion: str = Field(..., min_length=5)
    scene_index: int = Field(..., ge=0)
    timestamp_seconds: Optional[float] = None


class CritiqueResult(BaseModel):
    """Result of a critique evaluation."""

    run_id: str = Field(default="")
    iteration: int = Field(default=0)
    overall_score: float = Field(..., ge=0, le=1)
    passed: bool = Field(default=False)
    issues: list[CritiqueIssue] = Field(default_factory=list)
    per_scene_scores: dict[int, float] = Field(default_factory=dict)
    summary: str = Field(default="")

    def get_critical_issues(self) -> list[CritiqueIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    def get_major_issues(self) -> list[CritiqueIssue]:
        return [i for i in self.issues if i.severity == "major"]


# ═══════════════════════════════════════════════════════════════════════════
# DIRECTOR RUN STATE
# ═══════════════════════════════════════════════════════════════════════════

class DirectorRunStatus(str):
    PLANNING = "planning"
    GENERATING = "generating"
    CRITIQUING = "critiquing"
    RE_ROLLING = "re_rolling"
    COMPLETED = "completed"
    FAILED = "failed"


class DirectorRun(BaseModel):
    """Complete state of an autonomous director run."""

    id: str
    project_id: str

    # Input
    idea: str
    genre: str = "drama"
    target_duration: float = 60.0
    max_iterations: int = 3
    critic_threshold: float = 0.75

    # Plan
    plan: Optional[DirectorPlan] = None

    # Runtime state
    status: str = DirectorRunStatus.PLANNING
    current_iteration: int = 0
    current_scene_index: int = 0

    # Results
    critique_history: list[CritiqueResult] = Field(default_factory=list)
    final_clips: list[str] = Field(default_factory=list)  # Paths to final clips
    final_audio: list[str] = Field(default_factory=list)

    # Continuity
    continuity_state: ContinuityState = Field(default_factory=ContinuityState)

    # Outputs
    edl_path: Optional[str] = None
    fcpxml_path: Optional[str] = None
    premiere_xml_path: Optional[str] = None
    davinci_drt_path: Optional[str] = None
    prores_master_path: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    total_generations: int = 0
    total_re_rolls: int = 0
    error_message: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class DirectorRunEvent(BaseModel):
    """SSE event for director run progress."""

    run_id: str
    event_type: str  # "planning" | "generating_scene" | "scene_done" | "critiquing" | "re_rolling" | "completed" | "error"
    iteration: int
    scene_index: Optional[int] = None
    beat_slug: Optional[str] = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)