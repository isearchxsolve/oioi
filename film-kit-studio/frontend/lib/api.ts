// ── API client for Film Kit Studio backend ─────────────────

import type {
  Character,
  CharacterCreate,
  CharacterUpdate,
  Constants,
  Project,
  ProjectCreate,
  SceneUpdate,
  TaskInfo,
  DirectorRunRequest,
  DirectorRunResponse,
  DirectorRun,
  DirectorRunEvent,
  DirectorReport,
  LoRATrainingJob,
  TrainingJobStatus,
  ModelRegistryResponse,
  TrainingConfigRequest,
} from './types';

const API_BASE = '/api';

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const errorBody = await res.text();
    let message = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(errorBody);
      message = parsed.detail || message;
    } catch {
      // keep default
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function fetchMultipart<T>(url: string, formData: FormData): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const errorBody = await res.text();
    let message = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(errorBody);
      message = parsed.detail || message;
    } catch {
      // keep default
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Projects ───────────────────────────────────────────────

export const api = {
  // Projects
  listProjects: () => fetchJSON<Project[]>(`${API_BASE}/projects`),

  getProject: (id: string) => fetchJSON<Project>(`${API_BASE}/projects/${id}`),

  createProject: (data: ProjectCreate) =>
    fetchJSON<Project>(`${API_BASE}/projects`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProject: (id: string, data: Partial<ProjectCreate>) =>
    fetchJSON<Project>(`${API_BASE}/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteProject: (id: string) =>
    fetchJSON<void>(`${API_BASE}/projects/${id}`, { method: 'DELETE' }),

  updateScene: (projectId: string, sceneId: string, data: SceneUpdate) =>
    fetchJSON(`${API_BASE}/projects/${projectId}/scenes/${sceneId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  reorderScenes: (projectId: string, sceneIds: string[]) =>
    fetchJSON(`${API_BASE}/projects/${projectId}/scenes/reorder`, {
      method: 'POST',
      body: JSON.stringify(sceneIds),
    }),

  // Characters
  listCharacters: (projectId: string) =>
    fetchJSON<Character[]>(`${API_BASE}/projects/${projectId}/characters`),

  createCharacter: (projectId: string, data: CharacterCreate) =>
    fetchJSON<Character>(`${API_BASE}/projects/${projectId}/characters`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getCharacter: (projectId: string, charId: string) =>
    fetchJSON<Character>(`${API_BASE}/projects/${projectId}/characters/${charId}`),

  updateCharacter: (projectId: string, charId: string, data: CharacterUpdate) =>
    fetchJSON<Character>(`${API_BASE}/projects/${projectId}/characters/${charId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  uploadCharacterImage: (projectId: string, charId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchMultipart<Character>(`${API_BASE}/projects/${projectId}/characters/${charId}/image`, formData);
  },

  deleteCharacter: (projectId: string, charId: string) =>
    fetchJSON<void>(`${API_BASE}/projects/${projectId}/characters/${charId}`, {
      method: 'DELETE',
    }),

  // Pipeline triggers
  triggerScript: (projectId: string, numScenes: number) =>
    fetchJSON<TaskInfo>(`${API_BASE}/pipeline/${projectId}/script`, {
      method: 'POST',
      body: JSON.stringify({ num_scenes: numScenes }),
    }),

  triggerVisuals: (projectId: string, sceneIndices?: number[]) =>
    fetchJSON<TaskInfo>(`${API_BASE}/pipeline/${projectId}/visuals`, {
      method: 'POST',
      body: JSON.stringify({ scene_indices: sceneIndices ?? null }),
    }),

  triggerAudio: (projectId: string, voice?: string) =>
    fetchJSON<TaskInfo>(`${API_BASE}/pipeline/${projectId}/audio`, {
      method: 'POST',
      body: JSON.stringify({ voice: voice ?? null }),
    }),

  triggerClips: (projectId: string) =>
    fetchJSON<TaskInfo>(`${API_BASE}/pipeline/${projectId}/clips`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  triggerStitch: (projectId: string, mode: string = 'cut') =>
    fetchJSON<TaskInfo>(`${API_BASE}/pipeline/${projectId}/stitch`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),

  triggerFullPipeline: (projectId: string, numScenes: number, mode: string = 'cut') =>
    fetchJSON<TaskInfo>(`${API_BASE}/pipeline/${projectId}/full`, {
      method: 'POST',
      body: JSON.stringify({ num_scenes: numScenes, mode }),
    }),

  // Task monitoring
  getTask: (taskId: string) => fetchJSON<TaskInfo>(`${API_BASE}/pipeline/tasks/${taskId}`),

  // Constants
  getConstants: () => fetchJSON<Constants>(`${API_BASE}/constants`),

  // Health
  healthCheck: () => fetchJSON<{ status: string; ffmpeg_available: boolean }>(`${API_BASE}/health`),

  // Media URLs
  imageUrl: (projectId: string, filename: string) =>
    `${API_BASE}/media/image/${projectId}/${filename}`,
  clipUrl: (projectId: string, filename: string) =>
    `${API_BASE}/media/clip/${projectId}/${filename}`,
  videoUrl: (projectId: string, filename: string) =>
    `${API_BASE}/media/video/${projectId}/${filename}`,
  srtUrl: (projectId: string, filename: string) =>
    `${API_BASE}/media/srt/${projectId}/${filename}`,

  // ── Director Agent (M1) ────────────────────────────────────
  startDirectorRun: (data: DirectorRunRequest) =>
    fetchJSON<DirectorRunResponse>(`${API_BASE}/director/run`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getDirectorRun: (runId: string) =>
    fetchJSON<DirectorRun>(`${API_BASE}/director/${runId}/status`),

  getDirectorReport: (runId: string) =>
    fetchJSON<DirectorReport>(`${API_BASE}/director/${runId}/report`),

  cancelDirectorRun: (runId: string) =>
    fetchJSON<{ message: string }>(`${API_BASE}/director/${runId}/cancel`, {
      method: 'POST',
    }),

  listDirectorRuns: (projectId?: string) =>
    fetchJSON<DirectorRun[]>(`${API_BASE}/director/runs` + (projectId ? `?project_id=${projectId}` : '')),

  // Director file downloads
  downloadEDL: (runId: string) => `${API_BASE}/director/${runId}/edl`,
  downloadFCPXML: (runId: string) => `${API_BASE}/director/${runId}/fcpxml`,
  downloadPremiereXML: (runId: string) => `${API_BASE}/director/${runId}/premiere`,
  downloadDaVinciDRT: (runId: string) => `${API_BASE}/director/${runId}/davinci`,

  // Director SSE events
  directorEventSource: (runId: string) => `${API_BASE}/director/${runId}/events`,

  // ── Training (M2) ──────────────────────────────────────────
  startTraining: (data: TrainingConfigRequest & { project_id: string; character_id: string; backend?: string }) =>
    fetchJSON<LoRATrainingJob>(`${API_BASE}/training/lora/train`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTrainingStatus: (jobId: string) =>
    fetchJSON<LoRATrainingJob>(`${API_BASE}/training/lora/${jobId}/status`),

  listTrainingJobs: (projectId?: string, characterId?: string, status?: string) =>
    fetchJSON<LoRATrainingJob[]>(`${API_BASE}/training/jobs` + 
      new URLSearchParams({
        ...(projectId ? { project_id: projectId } : {}),
        ...(characterId ? { character_id: characterId } : {}),
        ...(status ? { status: status } : {}),
      }).toString()),

  cancelTraining: (jobId: string) =>
    fetchJSON<{ message: string }>(`${API_BASE}/training/lora/${jobId}/cancel`, {
      method: 'POST',
    }),

  downloadLoRA: (jobId: string) => `${API_BASE}/training/lora/${jobId}/download`,

  curateDataset: (data: {
    project_id: string;
    character_id: string;
    video_paths: string[];
    reference_images: string[];
    target_count: number;
    caption_template: string;
  }) =>
    fetchJSON<{
      dataset_dir: string;
      image_count: number;
      metadata: Record<string, any>;
    }>(`${API_BASE}/training/dataset/curate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listModels: (projectId?: string, characterId?: string, activeOnly?: boolean) =>
    fetchJSON<ModelRegistryResponse[]>(`${API_BASE}/training/models` + 
      new URLSearchParams({
        ...(projectId ? { project_id: projectId } : {}),
        ...(characterId ? { character_id: characterId } : {}),
        ...(activeOnly !== undefined ? { active_only: String(activeOnly) } : {}),
      }).toString()),

  getModel: (modelId: string) =>
    fetchJSON<ModelRegistryResponse>(`${API_BASE}/training/models/${modelId}`),

  deactivateModel: (modelId: string) =>
    fetchJSON<{ message: string }>(`${API_BASE}/training/models/${modelId}/deactivate`, {
      method: 'POST',
    }),

  deleteModel: (modelId: string, deleteFile?: boolean) =>
    fetchJSON<{ message: string }>(`${API_BASE}/training/models/${modelId}` + (deleteFile ? `?delete_file=${deleteFile}` : ''), {
      method: 'DELETE',
    }),

  getCharacterLoRA: (characterId: string, projectId?: string) =>
    fetchJSON<{ character_id: string; lora_path: string; lora_scale: number }>(
      `${API_BASE}/training/characters/${characterId}/lora` + (projectId ? `?project_id=${projectId}` : '')
    ),
};
