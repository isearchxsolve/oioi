'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { Project } from '@/lib/types';

export default function HomePage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const data = await api.listProjects();
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete project "${name}"? This cannot be undone.`)) return;
    try {
      await api.deleteProject(id);
      setProjects(projects.filter((p) => p.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete project');
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold text-lg">
              F
            </div>
            <div>
              <h1 className="text-xl font-bold">Film Kit Studio</h1>
              <p className="text-xs text-[var(--text-secondary)]">AI Filmmaking Platform</p>
            </div>
          </div>
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            <span className="text-lg">+</span> New Project
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            {error}
            <button className="ml-2 underline" onClick={() => setError('')}>dismiss</button>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
          </div>
        ) : projects.length === 0 && !showCreate ? (
          <div className="text-center py-20">
            <div className="text-6xl mb-4">🎬</div>
            <h2 className="text-2xl font-bold mb-2">No projects yet</h2>
            <p className="text-[var(--text-secondary)] mb-6">
              Create your first AI-generated film project to get started.
            </p>
            <button className="btn-primary" onClick={() => setShowCreate(true)}>
              <span className="text-lg">+</span> Create New Project
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {projects.map((project) => (
              <div
                key={project.id}
                className="glass-panel p-5 cursor-pointer hover:border-brand-500 transition-all group"
                onClick={() => router.push(`/projects/${project.id}`)}
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="font-bold text-lg truncate flex-1 group-hover:text-brand-400 transition-colors">
                    {project.name}
                  </h3>
                  <span className={`status-badge status-${project.status} ml-2 shrink-0`}>
                    {project.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-4 min-h-[2.5rem]">
                  {project.idea || 'No idea specified'}
                </p>
                <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
                  <span>📐 {project.aspect}</span>
                  <span>🎬 {project.num_scenes} scenes</span>
                  <span>🎙️ {project.voice}</span>
                </div>
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-[var(--border-color)]">
                  <span className="text-xs text-[var(--text-secondary)]">
                    {new Date(project.created_at).toLocaleDateString()}
                  </span>
                  <button
                    className="btn-danger text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(project.id, project.name);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Create modal */}
      {showCreate && (
        <CreateProjectModal
          onClose={() => setShowCreate(false)}
          onCreated={(id) => router.push(`/projects/${id}`)}
        />
      )}
    </div>
  );
}

// ── Create Project Modal ───────────────────────────────────

function CreateProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [name, setName] = useState('');
  const [idea, setIdea] = useState('');
  const [style, setStyle] = useState('cinematic, warm lighting, detailed');
  const [aspect, setAspect] = useState('16:9');
  const [voice, setVoice] = useState('aria');
  const [numScenes, setNumScenes] = useState(6);
  const [transitionMode, setTransitionMode] = useState('cut');
  const [music, setMusic] = useState(false);
  const [musicMood, setMusicMood] = useState('ambient');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const voices: Record<string, string> = {
    aria: 'Aria (US Female)',
    guy: 'Guy (US Male)',
    jenny: 'Jenny (US Female)',
    sonia: 'Sonia (UK Female)',
    ryan: 'Ryan (UK Male)',
    natasha: 'Natasha (AU Female)',
  };

  const styles = [
    'cinematic, warm lighting, detailed',
    'anime, vibrant colors, cel-shaded',
    'film noir, high contrast, black and white',
    'watercolor, soft pastels, painterly',
    'photorealistic, natural lighting, 8k',
    'cyberpunk, neon, futuristic, moody',
    'fantasy, ethereal, magical atmosphere',
    'documentary, realistic, handheld camera',
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Project name is required');
      return;
    }
    setCreating(true);
    setError('');
    try {
      const project = await api.createProject({
        name: name.trim(),
        idea: idea.trim(),
        style,
        aspect,
        voice,
        num_scenes: numScenes,
        transition_mode: transitionMode,
        music,
        music_mood: musicMood,
      });
      onCreated(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
      setCreating(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content w-full max-w-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">Create New Project</h2>
          <button onClick={onClose} className="text-[var(--text-secondary)] hover:text-white text-2xl leading-none">
            ×
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label-text">Project Name *</label>
            <input
              className="input-field"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My AI Film"
              autoFocus
            />
          </div>

          <div>
            <label className="label-text">Story Idea</label>
            <textarea
              className="input-field min-h-[100px] resize-y"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder="Describe your film idea... e.g., 'A lonely lighthouse keeper discovers a message in a bottle that changes everything.'"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-text">Visual Style</label>
              <select className="input-field" value={style} onChange={(e) => setStyle(e.target.value)}>
                {styles.map((s) => (
                  <option key={s} value={s}>{s.split(',')[0]}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label-text">Aspect Ratio</label>
              <select className="input-field" value={aspect} onChange={(e) => setAspect(e.target.value)}>
                <option value="16:9">16:9 (Landscape)</option>
                <option value="9:16">9:16 (Portrait)</option>
                <option value="1:1">1:1 (Square)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-text">Narration Voice</label>
              <select className="input-field" value={voice} onChange={(e) => setVoice(e.target.value)}>
                {Object.entries(voices).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label-text">Number of Scenes</label>
              <input
                type="number"
                className="input-field"
                value={numScenes}
                min={1}
                max={20}
                onChange={(e) => setNumScenes(parseInt(e.target.value) || 6)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-text">Transition Mode</label>
              <select className="input-field" value={transitionMode} onChange={(e) => setTransitionMode(e.target.value)}>
                <option value="cut">Cut (hard cut)</option>
                <option value="crossfade">Crossfade (smooth)</option>
              </select>
            </div>
            <div>
              <label className="label-text">Background Music</label>
              <div className="flex items-center gap-3 mt-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={music}
                    onChange={(e) => setMusic(e.target.checked)}
                    className="w-4 h-4 accent-brand-500"
                  />
                  <span className="text-sm">Add music</span>
                </label>
                {music && (
                  <select className="input-field flex-1" value={musicMood} onChange={(e) => setMusicMood(e.target.value)}>
                    <option value="ambient">Ambient</option>
                    <option value="tense">Tense</option>
                    <option value="bright">Bright</option>
                  </select>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={creating}>
              {creating ? <span className="spinner" /> : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
