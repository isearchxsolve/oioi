"use client";

import { useState, useMemo } from "react";
import { Scene } from "@/lib/types";
import { api } from "@/lib/api";

interface ReviewPanelProps {
  projectId: string;
  scenes: Scene[];
  onSceneUpdate: (sceneId: string, updates: Partial<Scene>) => Promise<void>;
  onReorder: (sceneIds: string[]) => Promise<void>;
}

export function ReviewPanel({ projectId, scenes, onSceneUpdate, onReorder }: ReviewPanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [updating, setUpdating] = useState<string | null>(null);

  const includedScenes = scenes.filter((s) => s.included);
  const excludedScenes = scenes.filter((s) => !s.included);

  const handleToggleInclude = async (scene: Scene) => {
    setUpdating(scene.id);
    try {
      await onSceneUpdate(scene.id, { included: !scene.included });
    } finally {
      setUpdating(null);
    }
  };

  const handleTrimChange = async (scene: Scene, field: "trim_start_seconds" | "trim_end_seconds", value: number) => {
    if (value < 0) return;
    setUpdating(scene.id);
    try {
      await onSceneUpdate(scene.id, { [field]: value });
    } finally {
      setUpdating(null);
    }
  };

  const handleTransitionChange = async (scene: Scene, value: string) => {
    setUpdating(scene.id);
    try {
      await onSceneUpdate(scene.id, { transition_type: value });
    } finally {
      setUpdating(null);
    }
  };

  const handleTransitionDurationChange = async (scene: Scene, value: number) => {
    if (value < 0 || value > 5) return;
    setUpdating(scene.id);
    try {
      await onSceneUpdate(scene.id, { transition_duration: value });
    } finally {
      setUpdating(null);
    }
  };

  const handleDragStart = (e: React.DragEvent, scene: Scene) => {
    e.dataTransfer.setData("sceneId", scene.id);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = async (e: React.DragEvent, targetScene: Scene) => {
    e.preventDefault();
    const draggedId = e.dataTransfer.getData("sceneId");
    if (!draggedId || draggedId === targetScene.id) return;

    const draggedIndex = scenes.findIndex((s) => s.id === draggedId);
    const targetIndex = scenes.findIndex((s) => s.id === targetScene.id);
    if (draggedIndex === -1 || targetIndex === -1) return;

    const newOrder = [...scenes];
    const [dragged] = newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, dragged);

    await onReorder(newOrder.map((s) => s.id));
  };

  const getClipUrl = (scene: Scene) => {
    if (!scene.clip_path) return null;
    return api.clipUrl(projectId, scene.clip_path.split("/").pop()!);
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          ✂️ Review & Edit
          <span className="text-xs px-2 py-0.5 bg-[var(--bg-tertiary)] rounded-full text-[var(--text-secondary)]">
            {includedScenes.length} / {scenes.length} included
          </span>
        </h3>
        <p className="text-xs text-[var(--text-secondary)]">
          Drag to reorder • Set trim points • Choose transitions
        </p>
      </div>

      {/* Included Scenes */}
      <div className="space-y-3">
        {includedScenes.map((scene, index) => (
          <ReviewSceneCard
            key={scene.id}
            scene={scene}
            index={index + 1}
            clipUrl={getClipUrl(scene)}
            isUpdating={updating === scene.id}
            expanded={expanded[scene.id]}
            onToggleExpand={() => setExpanded((prev) => ({ ...prev, [scene.id]: !prev[scene.id] }))}
            onToggleInclude={() => handleToggleInclude(scene)}
            onTrimChange={(field, value) => handleTrimChange(scene, field, value)}
            onTransitionChange={(value) => handleTransitionChange(scene, value)}
            onTransitionDurationChange={(value) => handleTransitionDurationChange(scene, value)}
            onDragStart={(e) => handleDragStart(e, scene)}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, scene)}
            formatTime={formatTime}
          />
        ))}

        {includedScenes.length === 0 && (
          <div className="p-6 text-center text-[var(--text-secondary)] border-2 border-dashed border-[var(--border-color)] rounded-lg">
            No scenes included. Enable scenes below or generate clips first.
          </div>
        )}
      </div>

      {/* Excluded Scenes */}
      {excludedScenes.length > 0 && (
        <details className="group">
          <summary className="flex items-center justify-between cursor-pointer p-3 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)]">
            <span className="font-medium">Excluded Scenes ({excludedScenes.length})</span>
            <svg className="w-5 h-5 text-[var(--text-secondary)] transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </summary>
          <div className="space-y-2 mt-2 p-2">
            {excludedScenes.map((scene) => (
              <div key={scene.id} className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded border border-[var(--border-color)] opacity-60">
                <span className="text-sm font-mono text-[var(--text-secondary)] w-8">#{scene.index + 1}</span>
                <span className="flex-1 text-sm truncate">{scene.narration || scene.visual_prompt}</span>
                <button
                  onClick={() => handleToggleInclude(scene)}
                  className="text-xs px-2 py-1 bg-green-500/20 text-green-400 border border-green-500/30 rounded hover:bg-green-500/30 transition-colors"
                >
                  Include
                </button>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

interface ReviewSceneCardProps {
  scene: Scene;
  index: number;
  clipUrl: string | null;
  isUpdating: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleInclude: () => void;
  onTrimChange: (field: "trim_start_seconds" | "trim_end_seconds", value: number) => void;
  onTransitionChange: (value: string) => void;
  onTransitionDurationChange: (value: number) => void;
  onDragStart: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  formatTime: (seconds: number) => string;
}

function ReviewSceneCard({
  scene,
  index,
  clipUrl,
  isUpdating,
  expanded,
  onToggleExpand,
  onToggleInclude,
  onTrimChange,
  onTransitionChange,
  onTransitionDurationChange,
  onDragStart,
  onDragOver,
  onDrop,
  formatTime,
}: ReviewSceneCardProps) {
  const clipDuration = scene.duration || 4;
  const trimStart = scene.trim_start_seconds ?? 0;
  const trimEnd = scene.trim_end_seconds ?? clipDuration;
  const effectiveDuration = Math.max(0, trimEnd - trimStart);

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className={`group p-3 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)] transition-all ${
        isUpdating ? "opacity-70" : ""
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-sm font-mono text-[var(--text-secondary)] w-8 flex-shrink-0">
          #{index}
        </span>
        <span className="flex-1 text-sm font-medium truncate">
          {scene.narration || "No narration"}
        </span>
        <button
          onClick={onToggleExpand}
          className="p-1 text-[var(--text-secondary)] hover:text-white transition-colors"
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          <svg className={`w-5 h-5 transition-transform ${expanded ? "rotate-90" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={scene.included}
            onChange={onToggleInclude}
            className="w-4 h-4 accent-[var(--accent)]"
          />
          <span className="text-[var(--text-secondary)]">Include</span>
        </label>
      </div>

      {/* Video Preview */}
      {clipUrl && (
        <div className="relative aspect-video bg-black rounded mb-3 overflow-hidden">
          <video
            src={clipUrl}
            className="w-full h-full object-cover"
            controls
            preload="metadata"
          />
          {/* Trim indicators */}
          {(trimStart > 0 || trimEnd < clipDuration) && (
            <div className="absolute bottom-0 left-0 right-0 h-2 bg-gradient-to-t from-black/60 to-transparent pointer-events-none">
              <div
                className="absolute top-0 h-full bg-red-400/50"
                style={{ width: `${(trimStart / clipDuration) * 100}%` }}
              />
              <div
                className="absolute top-0 right-0 h-full bg-red-400/50"
                style={{ width: `${((clipDuration - trimEnd) / clipDuration) * 100}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* Expanded Controls */}
      {expanded && (
        <div className="space-y-3 pt-3 border-t border-[var(--border-color)]">
          {/* Trim Controls */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-[var(--text-secondary)] mb-1">
                Trim Start (seconds)
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max={clipDuration}
                value={trimStart}
                onChange={(e) => onTrimChange("trim_start_seconds", parseFloat(e.target.value) || 0)}
                className="w-full px-2 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--text-secondary)] mb-1">
                Trim End (seconds)
              </label>
              <input
                type="number"
                step="0.1"
                min={0}
                max={clipDuration}
                value={trimEnd}
                onChange={(e) => onTrimChange("trim_end_seconds", parseFloat(e.target.value) || clipDuration)}
                className="w-full px-2 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>
          </div>

          <div className="text-xs text-[var(--text-secondary)]">
            Effective duration: <strong>{formatTime(effectiveDuration)}</strong> (original: {formatTime(clipDuration)})
          </div>

          {/* Transition Controls */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-[var(--text-secondary)] mb-1">
                Transition to Next
              </label>
              <select
                value={scene.transition_type || "inherit"}
                onChange={(e) => onTransitionChange(e.target.value)}
                className="w-full px-2 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              >
                <option value="inherit">Inherit (Project Default)</option>
                <option value="cut">Cut</option>
                <option value="crossfade">Crossfade</option>
                <option value="fade_to_black">Fade to Black</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-[var(--text-secondary)] mb-1">
                Duration (seconds)
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="5"
                value={scene.transition_duration ?? 0.5}
                onChange={(e) => onTransitionDurationChange(parseFloat(e.target.value) || 0.5)}
                className="w-full px-2 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}