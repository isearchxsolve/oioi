// ── TypeScript types matching backend schemas ──────────────

export interface Character {
  id: string;
  project_id: string;
  name: string;
  description: string;
  reference_image_path: string | null;
  created_at: string;
}

export interface Scene {
  id: string;
  project_id: string;
  index: number;
  narration: string;
  visual_prompt: string;
  // Cinematography direction (populated by the upgraded script prompt)
  shot_type: string | null;
  lens: string | null;
  lighting: string | null;
  camera_move: string | null;
  color_grade: string | null;
  // Review / trim / transition overrides (additive)
  trim_start_seconds: number | null;
  trim_end_seconds: number | null;
  transition_type: string | null;
  transition_duration: number | null;
  included: boolean;
  character_id: string | null;
  image_path: string | null;
  video_path: string | null;
  audio_path: string | null;
  clip_path: string | null;
  duration: number | null;
  status: string;
  error_message: string | null;
}

export interface Project {
  id: string;
  name: string;
  idea: string;
  style: string;
  aspect: string;
  voice: string;
  seed: number;
  music: boolean;
  music_mood: string;
  num_scenes: number;
  transition_mode: string;
  status: string;
  output_path: string | null;
  srt_path: string | null;
  created_at: string;
  updated_at: string;
  scenes: Scene[];
  characters: Character[];
}

export interface TaskInfo {
  id: string;
  project_id: string;
  task_type: string;
  status: string;
  progress: number;
  message: string;
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  idea: string;
  style: string;
  aspect: string;
  voice: string;
  num_scenes: number;
  music: boolean;
  music_mood: string;
  transition_mode: string;
  seed?: number;
}

export interface SceneUpdate {
  narration?: string;
  visual_prompt?: string;
  shot_type?: string;
  lens?: string;
  lighting?: string;
  camera_move?: string;
  color_grade?: string;
  trim_start_seconds?: number;
  trim_end_seconds?: number;
  transition_type?: string;
  transition_duration?: number;
  included?: boolean;
  character_id?: string | null;
}

export interface CharacterCreate {
  name: string;
  description: string;
}

export interface CharacterUpdate {
  name?: string;
  description?: string;
}

export interface Constants {
  aspects: Record<string, { width: number; height: number }>;
  voices: Record<string, string>;
  music_moods: string[];
  visual_styles: string[];
  providers: {
    script: string;
    visual: string;
    voice: string;
    music: string;
  };
}

export type SSEEvent =
  | { event: 'progress'; data: { progress: number; message: string } }
  | { event: 'scene_update'; data: { scene_id: string; status: string; [key: string]: unknown } }
  | { event: 'completed'; data: { result: Record<string, unknown> } }
  | { event: 'error'; data: { message: string } };

// ═══════════════════════════════════════════════════════════════
// DIRECTOR AGENT TYPES (M1)
// ═══════════════════════════════════════════════════════════════

export interface DirectorRunRequest {
  project_id: string;
  idea: string;
  genre: string;
  target_duration: number;
  max_iterations: number;
  critic_threshold: number;
  use_existing_continuity: boolean;
}

export interface DirectorRunResponse {
  run_id: string;
  status: string;
  message: string;
}

export type DirectorRunStatus =
  | 'planning'
  | 'generating'
  | 'critiquing'
  | 're_rolling'
  | 'exporting'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface DirectorRunEvent {
  run_id: string;
  event_type: string;
  iteration: number;
  scene_index: number | null;
  beat_slug: string | null;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface DirectorRun {
  id: string;
  project_id: string;
  status: DirectorRunStatus;
  idea: string;
  genre: string;
  target_duration: number;
  max_iterations: number;
  critic_threshold: number;
  current_iteration: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  beats: Beat[];
  scene_specs: SceneSpec[];
  critique_history: CritiqueResult[];
  final_clips: string[];
  edl_path: string | null;
  fcpxml_path: string | null;
  premiere_xml_path: string | null;
  davinci_drt_path: string | null;
  prores_master_path: string | null;
  total_generations: number;
  total_re_rolls: number;
  latest_score?: number;
  latest_passed?: boolean;
}

export interface Beat {
  slug: string;
  type: 'opening' | 'inciting' | 'rising' | 'climax' | 'falling' | 'resolution' | 'stinger';
  title: string;
  description: string;
  duration_seconds: number;
  mood: string;
  characters: string[];
  location: string;
  time_of_day: string;
  cinematography_notes: string;
  audio_notes: string;
  target_score: number;
}

export interface SceneSpec {
  beat_id: string;
  index_in_beat: number;
  narration: string;
  visual_prompt: string;
  shot_type: string;
  lens: string;
  lighting: string;
  camera_move: string;
  color_grade: string;
  duration_seconds: number;
  characters: string[];
  location: string;
  time_of_day: string;
  reference_images: string[];
  controlnet_inputs: Record<string, string>;
  lora_paths: Record<string, string>;
  audio_cues: string[];
  transition_in: string;
  transition_out: string;
}

export interface CritiqueIssue {
  type: string;
  severity: 'critical' | 'major' | 'minor' | 'suggestion';
  description: string;
  fix_suggestion: string;
  scene_index: number;
  timestamp_seconds: number | null;
}

export interface CritiqueResult {
  run_id: string;
  iteration: number;
  overall_score: number;
  passed: boolean;
  issues: CritiqueIssue[];
  per_scene_scores: Record<number, number>;
  summary: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// M2: CONTROLNET & VISUAL CONTROL TYPES
// ═══════════════════════════════════════════════════════════════════════════

export type ControlNetType = 
  | 'canny'
  | 'depth'
  | 'openpose'
  | 'normal'
  | 'lineart'
  | 'tile'
  | 'qrcode';

export interface ControlNetInput {
  type: ControlNetType;
  image_url: string;
  scale: number;
  guidance_start: number;
  guidance_end: number;
}

export interface LoRASpec {
  character_name: string;
  lora_path: string;
  scale: number;
}

export interface DirectorReport {
  run_id: string;
  final_score: number;
  passed: boolean;
  iterations_run: number;
  total_generations: number;
  total_re_rolls: number;
  critique_history: {
    iteration: number;
    overall_score: number;
    passed: boolean;
    issues: CritiqueIssue[];
    per_scene_scores: Record<number, number>;
    summary: string;
  }[];
  continuity_report: Record<string, unknown>;
}

export interface TrainingConfigRequest {
  base_model: string;
  model_type: string;
  resolution: number;
  batch_size: number;
  lora_rank: number;
  lora_alpha: number;
  lora_dropout: number;
  max_train_steps: number;
  learning_rate: number;
  lr_scheduler: string;
  lr_warmup_steps: number;
  optimizer: string;
  mixed_precision: string;
  gradient_accumulation_steps: number;
  gpu_type: string;
  num_gpus: number;
  output_dir: string;
  save_every_n_steps: number;
  save_precision: string;
}

export interface TrainingJobStatus {
  job_id: string;
  character_id: string;
  project_id: string;
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current_step: number;
  max_steps: number;
  logs: string[];
  lora_path: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface LoRATrainingJob extends TrainingJobStatus {
  config: TrainingConfigRequest;
  lora_path: string | null;
  error_message: string | null;
  total_generations?: number;
  total_re_rolls?: number;
}

export interface ModelRegistryResponse {
  model_id: string;
  character_id: string;
  character_name: string;
  project_id: string;
  lora_path: string;
  created_at: string;
  file_size: number;
  checksum: string;
  is_active: boolean;
}

export interface LoRAModelResponse {
  model_id: string;
  character_id: string;
  character_name: string;
  project_id: string;
  lora_path: string;
  created_at: string;
  file_size: number;
  checksum: string;
  is_active: boolean;
}
