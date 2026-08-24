"use client";

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { LoRATrainingJob, TrainingJobStatus, ModelRegistryResponse, TrainingConfigRequest } from '@/lib/types';

interface TrainingDashboardProps {
  projectId: string;
}

export function TrainingDashboard({ projectId }: TrainingDashboardProps) {
  const [jobs, setJobs] = useState<LoRATrainingJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<LoRATrainingJob | null>(null);
  const [models, setModels] = useState<ModelRegistryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'jobs' | 'models' | 'create'>('jobs');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [jobsRes, modelsRes] = await Promise.all([
        api.listTrainingJobs(projectId),
        api.listModels(projectId),
      ]);
      setJobs(jobsRes);
      setModels(modelsRes);
    } catch (err) {
      setError('Failed to load training data');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStartTraining = async (data: {
    character_id: string;
    config: TrainingConfigRequest;
    backend: string;
  }) => {
    try {
      const job = await api.startTraining({
        project_id: projectId,
        character_id: data.character_id,
        ...data.config,
        backend: data.backend,
      });
      // Poll for status updates
      const pollInterval = setInterval(async () => {
        const status = await api.getTrainingStatus(job.job_id);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(pollInterval);
          fetchData();
        }
      }, 5000);
    } catch (err) {
      setError('Failed to start training');
    }
  };

  if (loading) {
    return (
      <div className="glass-panel p-8 text-center">
        <div className="spinner mx-auto mb-4" style={{ width: 32, height: 32 }} />
        <p className="text-gray-400">Loading training dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel p-8 text-center text-red-400">
        <p>{error}</p>
        <button
          onClick={fetchData}
          className="mt-4 btn-secondary"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="glass-panel p-6 space-y-6">
      {/* Tab Navigation */}
      <div className="flex border-b border-white/10">
        {[
          { id: 'jobs', label: 'Training Jobs', icon: '🏃' },
          { id: 'models', label: 'LoRA Models', icon: '🤖' },
          { id: 'create', label: 'New Training', icon: '➕' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-brand-400 border-b-2 border-brand-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span className="flex items-center gap-1">
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </span>
          </button>
        ))}
      </div>

      {/* Jobs Tab */}
      {activeTab === 'jobs' && (
        <div className="space-y-4">
          {jobs.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <div className="text-4xl mb-2">🏃</div>
              <p>No training jobs yet</p>
              <button
                onClick={() => setActiveTab('create')}
                className="mt-4 btn-primary"
              >
                Create Your First Training Job
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {jobs.map((job) => (
                <TrainingJobCard
                  key={job.job_id}
                  job={job}
                  onSelect={setSelectedJob}
                  selected={selectedJob?.job_id === job.job_id}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Models Tab */}
      {activeTab === 'models' && (
        <div className="space-y-4">
          {models.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <div className="text-4xl mb-2">🤖</div>
              <p>No LoRA models registered</p>
              <p className="text-sm mt-2">Train a character to create a model</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {models.map((model) => (
                <ModelCard key={model.model_id} model={model} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create Training Tab */}
      {activeTab === 'create' && (
        <CreateTrainingForm
          projectId={projectId}
          onSubmit={handleStartTraining}
          onClose={() => setActiveTab('jobs')}
        />
      )}
    </div>
  );
}

function TrainingJobCard({
  job,
  onSelect,
  selected,
}: {
  job: LoRATrainingJob;
  onSelect: (job: LoRATrainingJob) => void;
  selected: boolean;
}) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-500/20 text-green-400';
      case 'failed': return 'bg-red-500/20 text-red-400';
      case 'running': return 'bg-yellow-500/20 text-yellow-400';
      case 'queued': return 'bg-blue-500/20 text-blue-400';
      default: return 'bg-gray-700 text-gray-400';
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  return (
    <div
      onClick={() => onSelect(job)}
      className={`p-4 rounded-lg cursor-pointer transition-all ${
        selected
          ? 'bg-brand-500/20 border border-brand-500/50 ring-1 ring-brand-500/20'
          : 'bg-white/5 border border-white/10 hover:border-brand-500/30'
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="text-2xl">🏃</div>
          <div>
            <h4 className="font-medium">Job {job.job_id}</h4>
            <p className="text-sm text-gray-400">
              Character: {job.character_id} • Project: {job.project_id}
            </p>
          </div>
        </div>
        <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(job.status)}`}>
          {job.status.toUpperCase()}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div className="bg-white/5 p-3 rounded">
          <div className="text-gray-400 text-xs">Progress</div>
          <div className="font-mono font-bold text-brand-400">
            {(job.progress * 100).toFixed(0)}%
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2 mt-1 overflow-hidden">
            <div
              className="bg-brand-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${job.progress * 100}%` }}
            />
          </div>
        </div>
        <div className="bg-white/5 p-3 rounded">
          <div className="text-gray-400 text-xs">Current Step</div>
          <div className="font-mono font-bold">
            {job.current_step} / {job.config.max_train_steps}
          </div>
        </div>
        <div className="bg-white/5 p-3 rounded">
          <div className="text-gray-400 text-xs">Elapsed</div>
          <div className="font-mono font-bold">
            {formatDuration(Math.floor(Date.now() / 1000) - new Date(job.created_at).getTime() / 1000)}
          </div>
        </div>
      </div>

      {job.error_message && (
        <div className="mt-3 p-3 bg-red-500/20 border border-red-500/30 rounded text-sm text-red-400">
          <strong>Error:</strong> {job.error_message}
        </div>
      )}

      {job.lora_path && (
        <div className="mt-3 p-3 bg-green-500/20 border border-green-500/30 rounded text-sm text-green-400">
          <strong>✅ Model Ready:</strong> {job.lora_path}
        </div>
      )}
    </div>
  );
}

function ModelCard({ model }: { model: ModelRegistryResponse }) {
  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="glass-panel p-4 space-y-3 border border-white/10 hover:border-brand-500/30 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-medium">{model.character_name}</h4>
          <p className="text-sm text-gray-400">{model.model_id}</p>
        </div>
        <span className="px-2 py-1 rounded text-xs font-medium bg-green-500/20 text-green-400">
          Active
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-white/5 p-2 rounded">
          <div className="text-gray-400 text-xs">File Size</div>
          <div className="font-mono">{formatBytes(model.file_size)}</div>
        </div>
        <div className="bg-white/5 p-2 rounded">
          <div className="text-gray-400 text-xs">Checksum</div>
          <div className="font-mono text-xs truncate">{model.checksum.slice(0, 16)}...</div>
        </div>
      </div>

      <div className="flex gap-2 pt-2">
        <button className="flex-1 btn-secondary text-sm">
          Download
        </button>
        <button className="flex-1 btn-secondary text-sm" disabled>
          Use in Generation
        </button>
      </div>
    </div>
  );
}

function CreateTrainingForm({
  projectId,
  onSubmit,
  onClose,
}: {
  projectId: string;
  onSubmit: (data: any) => void;
  onClose: () => void;
}) {
  const [characterId, setCharacterId] = useState('');
  const [backend, setBackend] = useState<'local' | 'modal' | 'runpod'>('local');
  const [config, setConfig] = useState({
    max_train_steps: 1000,
    learning_rate: 1e-4,
    lora_rank: 32,
    lora_alpha: 32,
    resolution: 512,
    batch_size: 1,
  });
  const [characters, setCharacters] = useState<Array<{ id: string; name: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fetch characters for the project
    // This would call api.listCharacters(projectId)
    setCharacters([
      { id: 'char-1', name: 'Hero' },
      { id: 'char-2', name: 'Villain' },
    ]);
  }, [projectId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await onSubmit({
        character_id: characterId,
        config,
        backend,
      });
      onClose();
    } catch (err) {
      setError('Failed to start training');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold">New Training Job</h3>
        <button
          type="button"
          onClick={onClose}
          className="p-2 text-gray-400 hover:text-white"
        >
          ✕
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-500/20 border border-red-500/30 rounded text-red-400 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label className="label-text">Character</label>
          <select
            value={characterId}
            onChange={(e) => setCharacterId(e.target.value)}
            className="input-field w-full"
            required
          >
            <option value="">Select a character</option>
            {characters.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label-text">Training Backend</label>
          <select
            value={backend}
            onChange={(e) => setBackend(e.target.value as any)}
            className="input-field w-full"
          >
            <option value="local">Local (GPU required)</option>
            <option value="modal">Modal.com (serverless)</option>
            <option value="runpod">RunPod (spot instances)</option>
          </select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label-text">Max Training Steps</label>
            <input
              type="number"
              value={config.max_train_steps}
              onChange={(e) => setConfig({ ...config, max_train_steps: parseInt(e.target.value) })}
              min={100}
              max={10000}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">Learning Rate</label>
            <input
              type="number"
              value={config.learning_rate}
              onChange={(e) => setConfig({ ...config, learning_rate: parseFloat(e.target.value) })}
              min={1e-6}
              max={1e-2}
              step={1e-5}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">LoRA Rank</label>
            <input
              type="number"
              value={config.lora_rank}
              onChange={(e) => setConfig({ ...config, lora_rank: parseInt(e.target.value) })}
              min={4}
              max={128}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">LoRA Alpha</label>
            <input
              type="number"
              value={config.lora_alpha}
              onChange={(e) => setConfig({ ...config, lora_alpha: parseInt(e.target.value) })}
              min={4}
              max={128}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">Resolution</label>
            <select
              value={config.resolution}
              onChange={(e) => setConfig({ ...config, resolution: parseInt(e.target.value) })}
              className="input-field"
            >
              <option value={512}>512x512</option>
              <option value={768}>768x768</option>
              <option value={1024}>1024x1024</option>
            </select>
          </div>

          <div>
            <label className="label-text">Batch Size</label>
            <input
              type="number"
              value={config.batch_size}
              onChange={(e) => setConfig({ ...config, batch_size: parseInt(e.target.value) })}
              min={1}
              max={4}
              className="input-field"
            />
          </div>
        </div>

        <div className="flex gap-3 pt-4 border-t border-white/10">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 btn-secondary"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!characterId || loading}
            className="flex-1 btn-primary"
          >
            {loading ? 'Starting...' : 'Start Training'}
          </button>
        </div>
      </div>
    </form>
  );
}