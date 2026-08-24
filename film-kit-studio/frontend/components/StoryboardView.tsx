'use client';

import { useRef, useState } from 'react';
import type { Project, Scene } from '@/lib/types';
import { api } from '@/lib/api';

interface StoryboardViewProps {
  project: Project;
  onSceneUpdate: (sceneId: string, data: { narration?: string; visual_prompt?: string; character_id?: string | null }) => void;
  onReorder: (sceneIds: string[]) => Promise<void>;
  disabled: boolean;
}

export function StoryboardView({ project, onSceneUpdate, onReorder, disabled }: StoryboardViewProps) {
  const [editingScene, setEditingScene] = useState<string | null>(null);
  const [editNarration, setEditNarration] = useState('');
  const [editVisualPrompt, setEditVisualPrompt] = useState('');

  // ── Drag-and-drop reorder state ────────────────────────────
  // Local copy of scene order so the UI updates instantly on drop,
  // before the persisted order comes back from the server.
  const [orderedScenes, setOrderedScenes] = useState<Scene[]>(project.scenes);
  const dragId = useRef<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // Keep local order in sync when the project reloads (e.g. after a
  // pipeline step) — but only when the set of scenes actually changes,
  // so we don't fight an in-flight reorder.
  const currentIds = project.scenes.map((s) => s.id).join('|');
  const localIds = orderedScenes.map((s) => s.id).join('|');
  if (currentIds !== localIds) {
    setOrderedScenes(project.scenes);
  }

  if (project.scenes.length === 0) {
    return (
      <div className="glass-panel p-12 text-center">
        <div className="text-5xl mb-4">📜</div>
        <h2 className="text-xl font-bold mb-2">No scenes yet</h2>
        <p className="text-[var(--text-secondary)]">
          Run <span className="text-brand-400 font-semibold">Generate Script</span> from the pipeline panel to create your storyboard.
        </p>
      </div>
    );
  }

  const startEdit = (scene: Scene) => {
    setEditingScene(scene.id);
    setEditNarration(scene.narration);
    setEditVisualPrompt(scene.visual_prompt);
  };

  const saveEdit = (sceneId: string) => {
    onSceneUpdate(sceneId, {
      narration: editNarration,
      visual_prompt: editVisualPrompt,
    });
    setEditingScene(null);
  };

  const handleCharacterChange = async (sceneId: string, charId: string) => {
    await onSceneUpdate(sceneId, { character_id: charId || null });
  };

  // ── Reorder handlers (HTML5 DnD) ───────────────────────────
  const handleDragStart = (e: React.DragEvent, sceneId: string) => {
    if (disabled) return;
    dragId.current = sceneId;
    setIsDragging(true);
    e.dataTransfer.effectAllowed = 'move';
    // Required for Firefox to initiate a drag
    e.dataTransfer.setData('text/plain', sceneId);
  };

  const handleDragEnd = () => {
    dragId.current = null;
    setDragOverId(null);
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent, sceneId: string) => {
    if (disabled || !dragId.current) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverId !== sceneId) setDragOverId(sceneId);
  };

  const handleDragLeave = (sceneId: string) => {
    if (dragOverId === sceneId) setDragOverId(null);
  };

  const handleDrop = async (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    const sourceId = dragId.current;
    handleDragEnd();

    if (!sourceId || sourceId === targetId) return;

    // Optimistic reorder locally
    const next = [...orderedScenes];
    const fromIdx = next.findIndex((s) => s.id === sourceId);
    const toIdx = next.findIndex((s) => s.id === targetId);
    if (fromIdx === -1 || toIdx === -1) return;

    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    // Re-sequence the visible scene numbers immediately
    next.forEach((s, i) => (s.index = i));
    setOrderedScenes(next);

    // Persist the new order
    try {
      await onReorder(next.map((s) => s.id));
    } catch {
      // Revert on failure — caller surfaces the error
      setOrderedScenes(project.scenes);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold">Storyboard</h2>
        <span className="text-sm text-[var(--text-secondary)]">
          {orderedScenes.length} scenes · {!disabled && 'drag to reorder'}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {orderedScenes.map((scene, idx) => {
          const isDropTarget = dragOverId === scene.id;
          return (
            <div
              key={scene.id}
              className={`scene-card ${isDragging && dragId.current === scene.id ? 'scene-card--dragging' : ''} ${isDropTarget ? 'scene-card--drop-target' : ''}`}
              draggable={!disabled}
              onDragStart={(e) => handleDragStart(e, scene.id)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, scene.id)}
              onDragLeave={() => handleDragLeave(scene.id)}
              onDrop={(e) => handleDrop(e, scene.id)}
            >
              {/* Image */}
                  <div className="relative aspect-video bg-[var(--bg-tertiary)] overflow-hidden">
                {/* Cinematography direction badges */}
                <div className="absolute bottom-2 left-2 flex flex-wrap gap-1 z-10">
                  {scene.shot_type && (
                    <span className="bg-black/50 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] font-mono text-blue-300">
                      {scene.shot_type}
                    </span>
                  )}
                  {scene.lens && (
                    <span className="bg-black/50 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] font-mono text-purple-300">
                      {scene.lens}
                    </span>
                  )}
                  {scene.lighting && (
                    <span className="bg-black/50 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] font-mono text-amber-300">
                      {scene.lighting}
                    </span>
                  )}
                  {scene.camera_move && (
                    <span className="bg-black/50 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] font-mono text-teal-300">
                      {scene.camera_move}
                    </span>
                  )}
                  {scene.color_grade && (
                    <span className="bg-black/50 backdrop-blur-sm px-1.5 py-0.5 rounded text-[10px] font-mono text-rose-300">
                      {scene.color_grade}
                    </span>
                  )}
                </div>
                {scene.image_path ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={api.imageUrl(project.id, scene.image_path)}
                    alt={`Scene ${idx + 1}`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-[var(--text-secondary)]">
                    {scene.status === 'visual_pending' || scene.status === 'VISUAL_PENDING' ? (
                      <div className="flex flex-col items-center gap-2">
                        <div className="spinner" style={{ width: 24, height: 24 }} />
                        <span className="text-xs">Generating...</span>
                      </div>
                    ) : (
                      <span className="text-4xl opacity-30">🖼️</span>
                    )}
                  </div>
                )}
                {/* Drag handle (top-left), shown when reordering is allowed */}
                {!disabled && (
                  <div
                    className="drag-handle absolute top-2 left-2 flex items-center gap-1 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-xs font-bold cursor-grab active:cursor-grabbing"
                    title="Drag to reorder"
                  >
                    <span className="drag-grip">⋮⋮</span>
                    <span>Scene {idx + 1}</span>
                  </div>
                )}
                {disabled && (
                  <div className="absolute top-2 left-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-xs font-bold">
                    Scene {idx + 1}
                  </div>
                )}
                <div className="absolute top-2 right-2">
                  <SceneStatusBadge status={scene.status} />
                </div>
              </div>

              {/* Content */}
              <div className="p-4 space-y-3">
                {editingScene === scene.id ? (
                  <div className="space-y-3">
                    <div>
                      <label className="label-text">Narration</label>
                      <textarea
                        className="input-field text-sm min-h-[60px] resize-y"
                        value={editNarration}
                        onChange={(e) => setEditNarration(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label-text">Visual Prompt</label>
                      <textarea
                        className="input-field text-sm min-h-[60px] resize-y"
                        value={editVisualPrompt}
                        onChange={(e) => setEditVisualPrompt(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="label-text">Character Reference</label>
                      <select
                        value={scene.character_id || ""}
                        onChange={(e) => handleCharacterChange(scene.id, e.target.value)}
                        className="input-field text-sm"
                      >
                        <option value="">None (project default)</option>
                        {project.characters?.map((char) => (
                          <option key={char.id} value={char.id}>
                            {char.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button className="btn-secondary text-xs" onClick={() => setEditingScene(null)}>Cancel</button>
                      <button className="btn-primary text-xs" onClick={() => saveEdit(scene.id)}>Save</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-1">
                        Narration
                      </div>
                      <p className="text-sm">{scene.narration || <span className="text-[var(--text-secondary)] italic">Not generated yet</span>}</p>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-1">
                        Visual Prompt
                      </div>
                      <p className="text-sm text-[var(--text-secondary)]">
                        {scene.visual_prompt || <span className="italic">Not generated yet</span>}
                      </p>
                    </div>
                    <div className="flex items-center justify-between pt-2 border-t border-[var(--border-color)]">
                      <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
                        {scene.audio_path && <span title="Audio ready">🎙️</span>}
                        {scene.clip_path && <span title="Clip ready">🎬</span>}
                        {scene.duration && <span>{scene.duration.toFixed(1)}s</span>}
                        {scene.character_id && <span title="Character assigned">👤</span>}
                      </div>
                      <button
                        className="btn-secondary text-xs px-2 py-1"
                        disabled={disabled}
                        onClick={() => startEdit(scene)}
                      >
                        ✏️ Edit
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SceneStatusBadge({ status }: { status: string }) {
  const statusMap: Record<string, { label: string; color: string }> = {
    pending: { label: 'Pending', color: 'bg-gray-500/30 text-gray-300' },
    script_done: { label: 'Script', color: 'bg-blue-500/30 text-blue-300' },
    visual_pending: { label: 'Visual...', color: 'bg-yellow-500/30 text-yellow-300' },
    visual_done: { label: 'Visual', color: 'bg-purple-500/30 text-purple-300' },
    audio_pending: { label: 'Audio...', color: 'bg-yellow-500/30 text-yellow-300' },
    audio_done: { label: 'Audio', color: 'bg-amber-500/30 text-amber-300' },
    clip_pending: { label: 'Clip...', color: 'bg-yellow-500/30 text-yellow-300' },
    clip_done: { label: 'Clip', color: 'bg-teal-500/30 text-teal-300' },
    error: { label: 'Error', color: 'bg-red-500/30 text-red-300' },
  };
  const info = statusMap[status] || statusMap.pending;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${info.color}`}>
      {info.label}
    </span>
  );
}
