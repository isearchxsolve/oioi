"use client";

import { useMemo } from 'react';
import type { DirectorRun, Beat, SceneSpec, CritiqueResult } from '@/lib/types';

interface DirectorTimelineProps {
  run: DirectorRun | null;
  selectedBeat?: string;
  onBeatSelect?: (beatSlug: string) => void;
}

const BEAT_TYPE_COLORS: Record<string, string> = {
  opening: 'bg-purple-500',
  inciting: 'bg-red-500',
  rising: 'bg-orange-500',
  climax: 'bg-yellow-500',
  falling: 'bg-blue-500',
  resolution: 'bg-green-500',
  stinger: 'bg-pink-500',
};

const BEAT_TYPE_LABELS: Record<string, string> = {
  opening: '🎬 Opening',
  inciting: '⚡ Inciting',
  rising: '📈 Rising',
  climax: '🔥 Climax',
  falling: '📉 Falling',
  resolution: '✅ Resolution',
  stinger: '🎁 Stinger',
};

export function DirectorTimeline({ run, selectedBeat, onBeatSelect }: DirectorTimelineProps) {
  if (!run || !run.beats?.length) {
    return (
      <div className="glass-panel p-8 text-center text-gray-500">
        <div className="text-4xl mb-2">📊</div>
        <p>No beat data yet. Start a director run to see the timeline.</p>
      </div>
    );
  }

  const totalDuration = run.beats.reduce((sum, b) => sum + (b.duration_seconds || 0), 0);

  return (
    <div className="glass-panel p-4 space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-lg">Beat Timeline</h3>
        <div className="text-sm text-gray-400">
          {run.beats.length} beats • ~{Math.round(totalDuration)}s
        </div>
      </div>

      {/* Timeline Visualization */}
      <div className="relative h-24">
        {/* Track */}
        <div className="absolute left-16 right-4 top-1/2 h-1 bg-gray-700 -translate-y-1/2 rounded" />

        {/* Beats */}
        <div className="relative h-full">
          {run.beats.map((beat, i) => {
            const startPct = run.beats.slice(0, i).reduce((sum, b) => sum + (b.duration_seconds || 0), 0) / totalDuration;
            const widthPct = (beat.duration_seconds || 0) / totalDuration;
            const leftPct = startPct * 100;
            const width = Math.max(2, widthPct * 100);

            return (
              <div
                key={beat.slug}
                className="absolute top-0 h-full transition-all duration-200 cursor-pointer"
                style={{
                  left: `${leftPct}%`,
                  width: `${width}%`,
                  minWidth: '30px',
                }}
                onClick={() => onBeatSelect?.(beat.slug)}
              >
                <div
                  className={`h-full ${BEAT_TYPE_COLORS[beat.type] || 'bg-gray-500'} rounded ${
                    selectedBeat === beat.slug ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-900 scale-y-150' : ''
                  }`}
                  title={`${BEAT_TYPE_LABELS[beat.type]}: ${beat.title}`}
                />
                {/* Beat label above */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 whitespace-nowrap text-xs text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
                  {BEAT_TYPE_LABELS[beat.type]}
                </div>
              </div>
            );
          })}
        </div>

        {/* Time markers */}
        <div className="absolute bottom-0 left-16 right-4 flex justify-between text-xs text-gray-500">
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => (
            <span key={pct} style={{ left: `${pct * 100}%` }} className="absolute -translate-x-1/2">
              {Math.round(pct * totalDuration)}s
            </span>
          ))}
        </div>
      </div>

      {/* Beat Details */}
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {run.beats.map((beat, i) => (
          <div
            key={beat.slug}
            className={`p-3 rounded-lg cursor-pointer transition-all ${
              selectedBeat === beat.slug
                ? 'bg-brand-500/20 border border-brand-500/50'
                : 'bg-white/5 border border-white/10 hover:border-brand-500/30'
            }`}
            onClick={() => onBeatSelect?.(beat.slug)}
          >
            <div className="flex items-center gap-3 mb-2">
              <span
                className={`w-2 h-2 rounded ${BEAT_TYPE_COLORS[beat.type] || 'bg-gray-500'}`}
              />
              <span className="font-medium">{BEAT_TYPE_LABELS[beat.type]}</span>
              <span className="text-sm text-gray-400">{beat.title}</span>
              <span className="ml-auto text-xs text-gray-500 font-mono">
                {(beat.duration_seconds || 0).toFixed(1)}s
              </span>
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono ${
                  beat.target_score >= 0.9 ? 'bg-green-500/20 text-green-400' :
                  beat.target_score >= 0.8 ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-red-500/20 text-red-400'
                }`}
              >
                Target: {(beat.target_score * 100).toFixed(0)}%
              </span>
            </div>

            <p className="text-sm text-gray-300 ml-5">{beat.description}</p>

            <div className="flex flex-wrap gap-2 mt-2 ml-5 text-xs text-gray-500">
              {beat.characters.length > 0 && (
                <span className="px-2 py-0.5 bg-gray-800 rounded">👥 {beat.characters.join(', ')}</span>
              )}
              <span className="px-2 py-0.5 bg-gray-800 rounded">📍 {beat.location}</span>
              <span className="px-2 py-0.5 bg-gray-800 rounded">🕐 {beat.time_of_day}</span>
              <span className="px-2 py-0.5 bg-gray-800 rounded">🎭 {beat.mood}</span>
            </div>

            {/* Scene specs for this beat */}
            {run.scene_specs && run.scene_specs.length > 0 && (
              <div className="mt-2 ml-5 space-y-1 border-l border-gray-700 pl-3">
                {run.scene_specs
                  .filter((s) => s.beat_id === beat.slug)
                  .map((scene, si) => (
                    <div
                      key={scene.beat_id + si}
                      className="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-200"
                    >
                      <span className="w-1 h-1 rounded-full bg-gray-500" />
                      <span>{scene.shot_type} • {scene.lens} • {scene.camera_move}</span>
                      <span className="text-gray-600">|</span>
                      <span className="font-mono">{scene.duration_seconds}s</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}