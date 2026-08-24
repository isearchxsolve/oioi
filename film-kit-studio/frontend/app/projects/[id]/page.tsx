'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useSSE } from '@/lib/useSSE';
import type { Project, Scene, TaskInfo } from '@/lib/types';
import { PipelinePanel } from '@/components/PipelinePanel';
import { StoryboardView } from '@/components/StoryboardView';
import { VideoPlayer } from '@/components/VideoPlayer';
import { DirectorPanel } from '@/components/DirectorPanel';

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTask, setActiveTask] = useState<TaskInfo | null>(null);
  const [taskProgress, setTaskProgress] = useState<{ progress: number; message: string } | null>(null);
  const [taskError, setTaskError] = useState('');
  const [providers, setProviders] = useState<{ visual: string; voice: string; music: string }>({ visual: 'cosmos', voice: 'edge', music: 'ffmpeg' });
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const loadProject = useCallback(async () => {
    try {
      const data = await api.getProject(projectId);
      setProject(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  // Load active provider tiers from the backend constants
  useEffect(() => {
    api.getConstants().then((c) => setProviders(c.providers)).catch(() => {});
  }, []);

  // SSE for active task
  const { connected } = useSSE(activeTask?.id ?? null, {
    onProgress: (progress, message) => {
      setTaskProgress({ progress, message });
    },
    onSceneUpdate: () => {
      // Refresh project data when a scene updates
      loadProject();
    },
    onCompleted: () => {
      setActiveTask(null);
      setTaskProgress(null);
      loadProject();
    },
    onError: (message) => {
      setTaskError(message);
      setActiveTask(null);
      setTaskProgress(null);
      loadProject();
    },
  });

  // Fallback polling if SSE disconnects
  useEffect(() => {
    if (activeTask && !connected) {
      pollRef.current = setInterval(async () => {
        try {
          const task = await api.getTask(activeTask.id);
          setTaskProgress({ progress: task.progress, message: task.message });
          if (task.status === 'completed') {
            setActiveTask(null);
            setTaskProgress(null);
            loadProject();
            if (pollRef.current) clearInterval(pollRef.current);
          } else if (task.status === 'failed') {
            setTaskError(task.message || 'Task failed');
            setActiveTask(null);
            setTaskProgress(null);
            loadProject();
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {
          // ignore polling errors
        }
      }, 2000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [activeTask, connected, loadProject]);

  const handleTrigger = async (action: 'script' | 'visuals' | 'audio' | 'clips' | 'stitch' | 'full') => {
    setTaskError('');
    try {
      let task: TaskInfo;
      switch (action) {
        case 'script':
          task = await api.triggerScript(projectId, project?.num_scenes ?? 6);
          break;
        case 'visuals':
          task = await api.triggerVisuals(projectId);
          break;
        case 'audio':
          task = await api.triggerAudio(projectId, project?.voice);
          break;
        case 'clips':
          task = await api.triggerClips(projectId);
          break;
        case 'stitch':
          task = await api.triggerStitch(projectId, project?.transition_mode ?? 'cut');
          break;
        case 'full':
          task = await api.triggerFullPipeline(projectId, project?.num_scenes ?? 6, project?.transition_mode ?? 'cut');
          break;
      }
      setActiveTask(task);
      setTaskProgress({ progress: 0, message: 'Starting...' });
    } catch (err) {
      setTaskError(err instanceof Error ? err.message : `Failed to trigger ${action}`);
    }
  };

  const handleSceneUpdate = async (sceneId: string, data: { narration?: string; visual_prompt?: string }) => {
    try {
      await api.updateScene(projectId, sceneId, data);
      loadProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update scene');
    }
  };

  const handleReorder = async (sceneIds: string[]) => {
    try {
      await api.reorderScenes(projectId, sceneIds);
      loadProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reorder scenes');
      throw err; // let StoryboardView revert its optimistic order
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <div className="text-red-400 mb-4">{error}</div>
        <button className="btn-secondary" onClick={() => router.push('/')}>Back to Projects</button>
      </div>
    );
  }

  if (!project) return null;

  const isBusy = !!activeTask;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-secondary)] sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/')}
              className="text-[var(--text-secondary)] hover:text-white transition-colors"
            >
              ← Back
            </button>
            <div className="h-6 w-px bg-[var(--border-color)]" />
            <div>
              <h1 className="text-lg font-bold">{project.name}</h1>
              <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
                <span className={`status-badge status-${project.status}`}>{project.status.replace(/_/g, ' ')}</span>
                <span>📐 {project.aspect}</span>
                <span>🎬 {project.num_scenes} scenes</span>
                <span>🎙️ {project.voice}</span>
                <span title="Active provider tiers" className="flex items-center gap-1">
                  <span className={`px-1.5 py-0.5 rounded ${providers.visual === 'cosmos' ? 'bg-gray-500/20 text-gray-400' : 'bg-emerald-500/20 text-emerald-300'}`}>vid:{providers.visual}</span>
                  <span className={`px-1.5 py-0.5 rounded ${providers.voice === 'edge' ? 'bg-gray-500/20 text-gray-400' : 'bg-emerald-500/20 text-emerald-300'}`}>vox:{providers.voice}</span>
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {taskProgress && (
              <div className="flex items-center gap-3 text-sm">
                <div className="w-48">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--text-secondary)]">{taskProgress.message}</span>
                    <span>{Math.round(taskProgress.progress * 100)}%</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-bar-fill" style={{ width: `${taskProgress.progress * 100}%` }} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Error banner */}
      {(error || taskError) && (
        <div className="max-w-7xl mx-auto px-6 mt-4">
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center justify-between">
            <span>{taskError || error}</span>
            <button onClick={() => { setError(''); setTaskError(''); }} className="underline">dismiss</button>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
        {/* Left: Storyboard / Video */}
        <div className="space-y-6">
          {project.output_path ? (
            <VideoPlayer project={project} />
          ) : null}

          <StoryboardView
            project={project}
            onSceneUpdate={handleSceneUpdate}
            onReorder={handleReorder}
            disabled={isBusy}
          />
        </div>

        {/* Right: Pipeline Panel + Director Panel */}
        <div className="lg:sticky lg:top-20 lg:self-start space-y-6">
          <PipelinePanel
            project={project}
            onTrigger={handleTrigger}
            isBusy={isBusy}
            activeTaskType={activeTask?.task_type ?? null}
          />
          <DirectorPanel projectId={projectId} />
        </div>
      </main>
    </div>
  );
}
