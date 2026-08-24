'use client';

import { useState } from 'react';
import type { Project } from '@/lib/types';
import { api } from '@/lib/api';

interface VideoPlayerProps {
  project: Project;
}

export function VideoPlayer({ project }: VideoPlayerProps) {
  const [showSubtitles, setShowSubtitles] = useState(true);

  if (!project.output_path) return null;

  const videoUrl = api.videoUrl(project.id, project.output_path);
  const srtUrl = project.srt_path ? api.srtUrl(project.id, project.srt_path) : null;

  return (
    <div className="glass-panel overflow-hidden">
      <div className="relative bg-black">
        <video
          controls
          className="w-full max-h-[500px]"
          src={videoUrl}
        >
          {showSubtitles && srtUrl && (
            <track
              kind="subtitles"
              src={srtUrl}
              srcLang="en"
              label="English"
              default
            />
          )}
        </video>
      </div>
      <div className="p-4 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-lg">Final Film</h2>
          <p className="text-xs text-[var(--text-secondary)]">
            {project.scenes.length} scenes · {project.aspect} · {project.transition_mode} transitions
          </p>
        </div>
        <div className="flex items-center gap-3">
          {srtUrl && (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={showSubtitles}
                onChange={(e) => setShowSubtitles(e.target.checked)}
                className="w-4 h-4 accent-brand-500"
              />
              Subtitles
            </label>
          )}
          <a href={videoUrl} download className="btn-secondary text-sm">
            ⬇ Download
          </a>
        </div>
      </div>
    </div>
  );
}
