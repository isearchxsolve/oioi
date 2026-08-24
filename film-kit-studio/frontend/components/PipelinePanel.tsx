'use client';

import { useState } from 'react';
import type { Project } from '@/lib/types';
import { api } from '@/lib/api';

interface PipelinePanelProps {
  project: Project;
  onTrigger: (action: 'script' | 'visuals' | 'audio' | 'clips' | 'stitch' | 'full') => void;
  isBusy: boolean;
  activeTaskType: string | null;
}

const STEPS = [
  { key: 'script', label: 'Generate Script', icon: '📝', desc: 'AI writes narration & visual prompts', requires: [] },
  { key: 'visuals', label: 'Generate Visuals', icon: '🎨', desc: 'Cosmos3 creates scene images', requires: ['script'] },
  { key: 'audio', label: 'Generate Audio', icon: '🎙️', desc: 'Edge-TTS narrates each scene', requires: ['script'] },
  { key: 'clips', label: 'Render Clips', icon: '🎬', desc: 'FFMPEG Ken Burns clip rendering', requires: ['visuals', 'audio'] },
  { key: 'stitch', label: 'Stitch Film', icon: '🎞️', desc: 'Combine clips into final film', requires: ['clips'] },
] as const;

export function PipelinePanel({ project, onTrigger, isBusy, activeTaskType }: PipelinePanelProps) {
  const [showFullConfirm, setShowFullConfirm] = useState(false);

  const isStepDone = (stepKey: string): boolean => {
    const statusOrder = ['draft', 'script_generated', 'visuals_generated', 'audio_generated', 'clips_generated', 'rendered'];
    const currentIdx = statusOrder.indexOf(project.status);
    const stepIdx = {
      script: 1,
      visuals: 2,
      audio: 3,
      clips: 4,
      stitch: 5,
    }[stepKey] ?? 0;
    return currentIdx >= stepIdx;
  };

  const isStepAvailable = (requires: readonly string[]): boolean => {
    if (requires.length === 0) return true;
    return requires.every((r) => isStepDone(r));
  };

  return (
    <div className="glass-panel p-5 space-y-4">
      <div>
        <h2 className="font-bold text-lg mb-1">Pipeline</h2>
        <p className="text-xs text-[var(--text-secondary)]">
          Run each step individually or generate the entire film at once.
        </p>
      </div>

      {/* Full pipeline button */}
      <div className="p-4 rounded-lg bg-gradient-to-br from-brand-500/10 to-brand-700/10 border border-brand-500/30">
        <button
          className="btn-primary w-full justify-center"
          disabled={isBusy}
          onClick={() => setShowFullConfirm(true)}
        >
          🚀 Generate Full Film
        </button>
        <p className="text-xs text-[var(--text-secondary)] mt-2 text-center">
          Runs all steps end-to-end automatically
        </p>
      </div>

      {/* Divider */}
      <div className="flex items-center gap-3">
        <div className="h-px bg-[var(--border-color)] flex-1" />
        <span className="text-xs text-[var(--text-secondary)]">OR RUN INDIVIDUAL STEPS</span>
        <div className="h-px bg-[var(--border-color)] flex-1" />
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {STEPS.map((step) => {
          const done = isStepDone(step.key);
          const available = isStepAvailable(step.requires);
          const isActive = activeTaskType === step.key;
          const disabled = isBusy || !available;

          return (
            <div
              key={step.key}
              className={`p-3 rounded-lg border transition-all ${
                done
                  ? 'border-green-500/30 bg-green-500/5'
                  : isActive
                  ? 'border-brand-500 bg-brand-500/10'
                  : available
                  ? 'border-[var(--border-color)] hover:border-brand-500/50'
                  : 'border-[var(--border-color)] opacity-50'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="text-2xl">{step.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{step.label}</span>
                    {done && <span className="text-green-400 text-xs">✓</span>}
                    {isActive && <span className="spinner" style={{ width: 12, height: 12 }} />}
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] truncate">{step.desc}</p>
                </div>
                <button
                  className="btn-secondary text-xs px-3 py-1.5"
                  disabled={disabled}
                  onClick={() => onTrigger(step.key)}
                >
                  {done ? 'Redo' : 'Run'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Project info */}
      <div className="pt-4 border-t border-[var(--border-color)] space-y-2 text-xs">
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Style</span>
          <span className="truncate ml-2 max-w-[200px]">{project.style}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Transition</span>
          <span>{project.transition_mode}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Music</span>
          <span>{project.music ? `Yes (${project.music_mood})` : 'No'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Seed</span>
          <span>{project.seed}</span>
        </div>
      </div>

      {/* Full pipeline confirmation modal */}
      {showFullConfirm && (
        <div className="modal-overlay" onClick={() => setShowFullConfirm(false)}>
          <div className="modal-content max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold mb-2">Generate Full Film?</h3>
            <p className="text-sm text-[var(--text-secondary)] mb-4">
              This will run the entire pipeline: script generation → visuals → audio → clips → stitching.
              This may take several minutes depending on the number of scenes.
            </p>
            <div className="flex justify-end gap-3">
              <button className="btn-secondary" onClick={() => setShowFullConfirm(false)}>Cancel</button>
              <button
                className="btn-primary"
                onClick={() => {
                  onTrigger('full');
                  setShowFullConfirm(false);
                }}
              >
                🚀 Start
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
