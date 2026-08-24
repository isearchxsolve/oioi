"use client";

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { api } from '@/lib/api';
import type {
  DirectorRunRequest,
  DirectorRun,
  DirectorRunEvent,
  DirectorRunStatus,
  DirectorReport,
  Beat,
  SceneSpec,
  CritiqueResult,
} from '@/lib/types';

const GENRES = [
  'drama',
  'thriller',
  'horror',
  'sci-fi',
  'cyberpunk',
  'noir',
  'comedy',
  'romance',
  'action',
  'fantasy',
  'documentary',
  'experimental',
];

const EVENT_TYPE_LABELS: Record<string, string> = {
  started: '🎬 Started',
  planning: '📝 Planning',
  generating_scene: '🎥 Generating Scene',
  scene_done: '✅ Scene Complete',
  critiquing: '👁️ Critiquing',
  re_rolling: '🔄 Re-rolling',
  completed: '🏁 Completed',
  error: '❌ Error',
};

export function DirectorPanel({ projectId }: { projectId: string }) {
  const [activeTab, setActiveTab] = useState<'config' | 'monitor' | 'report'>('config');
  const [isRunning, setIsRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<DirectorRun | null>(null);
  const [report, setReport] = useState<DirectorReport | null>(null);
  const [events, setEvents] = useState<DirectorRunEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Config form state
  const [idea, setIdea] = useState('');
  const [genre, setGenre] = useState('drama');
  const [targetDuration, setTargetDuration] = useState(60);
  const [maxIterations, setMaxIterations] = useState(3);
  const [criticThreshold, setCriticThreshold] = useState(0.75);

  const handleStartRun = async () => {
    if (!idea.trim()) {
      setError('Please enter a film idea/logline');
      return;
    }

    setError(null);
    setIsRunning(true);
    setEvents([]);

    try {
      const response = await api.startDirectorRun({
        project_id: projectId,
        idea: idea.trim(),
        genre,
        target_duration: targetDuration,
        max_iterations: maxIterations,
        critic_threshold: criticThreshold,
        use_existing_continuity: false,
      });

      setRunId(response.run_id);
      setActiveTab('monitor');
      connectToSSE(response.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start director run');
      setIsRunning(false);
    }
  };

  const connectToSSE = useCallback((id: string) => {
    const eventSource = new EventSource(api.directorEventSource(id));

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.run_id) {
          setRunStatus(data);
        }
      } catch {
        // Ignore parse errors
      }
    };

    eventSource.addEventListener('started', handleEvent);
    eventSource.addEventListener('planning', handleEvent);
    eventSource.addEventListener('generating_scene', handleEvent);
    eventSource.addEventListener('scene_done', handleEvent);
    eventSource.addEventListener('critiquing', handleEvent);
    eventSource.addEventListener('re_rolling', handleEvent);
    eventSource.addEventListener('completed', handleEvent);
    eventSource.addEventListener('error', handleEvent);
    eventSource.addEventListener('iteration_update', handleEvent);
    eventSource.addEventListener('critique_complete', handleEvent);

    eventSource.onerror = () => {
      eventSource.close();
      fetchFinalStatus(id);
    };

    // Store for cleanup
    (window as any).__directorEventSource = eventSource;
  }, []);

  const handleEvent = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as DirectorRunEvent;
      setEvents((prev) => [...prev, data]);
      
      // Update runStatus with event data
      setRunStatus((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          status: data.event_type as DirectorRunStatus,
          current_iteration: data.iteration,
          updated_at: data.timestamp,
        };
      });
    } catch {
      // Ignore
    }
  };

  const fetchFinalStatus = async (id: string) => {
    try {
      const status = await api.getDirectorRun(id);
      setRunStatus(status);
      if (status.status === 'completed' || status.status === 'failed') {
        const reportData = await api.getDirectorReport(id);
        setReport(reportData);
        setIsRunning(false);
      }
    } catch {
      setIsRunning(false);
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await api.cancelDirectorRun(runId);
      setIsRunning(false);
      setError('Run cancelled by user');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel');
    }
  };

  const downloadFile = (url: string, filename: string) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
  };

  const getStatusColor = (status: DirectorRunStatus | undefined) => {
    switch (status) {
      case 'completed': return 'text-green-400';
      case 'failed': return 'text-red-400';
      case 'planning': case 'generating': case 'critiquing': case 're_rolling':
        return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getProgressPercent = () => {
    if (!runStatus) return 0;
    if (runStatus.status === 'completed') return 100;
    if (runStatus.status === 'failed') return 0;
    const iter = runStatus.current_iteration || 0;
    const max = runStatus.max_iterations || 1;
    return Math.min(95, (iter / max) * 100);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      const es = (window as any).__directorEventSource;
      if (es) {
        es.close();
      }
    };
  }, []);

  return (
    <div className="glass-panel flex flex-col h-full">
      {/* Tab Bar */}
      <div className="flex border-b border-white/10">
        {[
          { id: 'config', label: '⚙️ Configure' },
          { id: 'monitor', label: '📊 Monitor' },
          { id: 'report', label: '📋 Report' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex-1 py-3 px-4 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-brand-400 border-b-2 border-brand-400'
                : 'text-gray-400 hover:text-white'
            }`}
            disabled={isRunning && tab.id === 'config'}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Config Tab */}
      {activeTab === 'config' && (
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div>
            <h3 className="text-lg font-bold mb-4">Film Idea / Logline</h3>
            <textarea
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder="A lone detective in neo-noir Tokyo hunts a memory thief who steals identities..."
              className="w-full input-field min-h-[100px] resize-y"
              rows={4}
            />
            <p className="text-xs text-gray-500 mt-1">
              Describe your film in 1-3 sentences. Include protagonist, conflict, setting, and tone.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-text">Genre</label>
              <select
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                className="input-field"
              >
                {GENRES.map((g) => (
                  <option key={g} value={g}>{g.charAt(0).toUpperCase() + g.slice(1)}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="label-text">Target Duration (seconds)</label>
              <input
                type="number"
                value={targetDuration}
                onChange={(e) => setTargetDuration(Number(e.target.value))}
                min={15}
                max={300}
                step={5}
                className="input-field"
              />
            </div>

            <div>
              <label className="label-text">Max Iterations</label>
              <input
                type="number"
                value={maxIterations}
                onChange={(e) => setMaxIterations(Number(e.target.value))}
                min={1}
                max={10}
                className="input-field"
              />
            </div>

            <div>
              <label className="label-text">Critic Threshold</label>
              <input
                type="range"
                value={criticThreshold}
                onChange={(e) => setCriticThreshold(Number(e.target.value))}
                min={0.5}
                max={1.0}
                step={0.05}
                className="w-full"
              />
              <div className="text-sm text-gray-400">{Math.round(criticThreshold * 100)}% score required to pass</div>
            </div>
          </div>

          {error && (
            <div className="bg-red-500/20 border border-red-500/30 text-red-300 p-3 rounded">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-4 border-t border-white/10">
            <button
              onClick={handleStartRun}
              disabled={!idea.trim() || isRunning}
              className="flex-1 btn-primary py-3 text-lg font-semibold"
            >
              {isRunning ? '🎬 Starting...' : '🎬 Start Autonomous Run'}
            </button>
          </div>
        </div>
      )}

      {/* Monitor Tab */}
      {activeTab === 'monitor' && (
        <div className="flex-1 flex flex-col">
          {runId && (
            <div className="p-4 border-b border-white/10 bg-white/5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className={`px-3 py-1 rounded text-sm font-mono ${getStatusColor(runStatus?.status)}`}>
                    {runStatus?.status?.toUpperCase() || 'STARTING'}
                  </span>
                  <span className="text-sm text-gray-400">Run: {runId}</span>
                  <span className="text-sm text-gray-400">
                    Iteration {runStatus?.current_iteration || 0} / {runStatus?.max_iterations || 3}
                  </span>
                </div>
                {isRunning && (
                  <button onClick={handleCancel} className="btn-secondary text-sm">
                    Cancel
                  </button>
                )}
              </div>
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all duration-300"
                  style={{ width: `${getProgressPercent()}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {events.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <div className="text-4xl mb-4">🎬</div>
                <p>Start a director run to see live progress</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[500px] overflow-y-auto">
                {events.map((event, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 animate-slide-in"
                  >
                    <span className="text-sm text-gray-400 font-mono min-w-[70px]">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      event.event_type === 'error' ? 'bg-red-500/20 text-red-400' :
                      event.event_type === 'completed' ? 'bg-green-500/20 text-green-400' :
                      event.event_type.includes('scene') ? 'bg-blue-500/20 text-blue-400' :
                      event.event_type.includes('critiq') ? 'bg-purple-500/20 text-purple-400' :
                      event.event_type.includes('re_roll') ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-gray-700 text-gray-300'
                    }`}>
                      {EVENT_TYPE_LABELS[event.event_type] || event.event_type}
                    </span>
                    <span className="flex-1 text-sm text-gray-300">{event.message}</span>
                    {event.data.score !== undefined && (
                      <span className="text-sm font-mono text-brand-400">
                        Score: {(Number(event.data.score) * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {runStatus?.status === 'completed' && (
              <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
                <h4 className="font-bold text-green-400 mb-2">✅ Run Completed Successfully!</h4>
                <p className="text-sm text-gray-300 mb-2">
                  Final Score: {((runStatus.latest_score ?? 0) * 100).toFixed(1)}%
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => downloadFile(api.downloadEDL(runId!), `director_${runId}.edl`)}
                    className="btn-secondary text-sm"
                  >
                    📥 Download EDL
                  </button>
                  <button
                    onClick={() => downloadFile(api.downloadFCPXML(runId!), `director_${runId}.fcpxml`)}
                    className="btn-secondary text-sm"
                  >
                    📥 Download FCPXML
                  </button>
                  <button
                    onClick={() => downloadFile(api.downloadPremiereXML(runId!), `director_${runId}.xml`)}
                    className="btn-secondary text-sm"
                  >
                    📥 Download Premiere XML
                  </button>
                  <button
                    onClick={() => downloadFile(api.downloadDaVinciDRT(runId!), `director_${runId}.drt`)}
                    className="btn-secondary text-sm"
                  >
                    📥 Download DaVinci DRT
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Report Tab */}
      {activeTab === 'report' && (
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {report ? (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-xl font-bold">Director Report</h3>
                <span className={`px-3 py-1 rounded text-sm font-mono ${
                  report.passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                }`}>
                  {report.passed ? 'PASSED' : 'NEEDS MORE WORK'}
                </span>
              </div>

              <div className="grid grid-cols-4 gap-4">
                <div className="glass-panel p-4 text-center">
                  <div className="text-3xl font-bold text-brand-400">
                    {(report.final_score * 100).toFixed(1)}%
                  </div>
                  <div className="text-sm text-gray-400">Final Score</div>
                </div>
                <div className="glass-panel p-4 text-center">
                  <div className="text-3xl font-bold text-yellow-400">{report.iterations_run}</div>
                  <div className="text-sm text-gray-400">Iterations Run</div>
                </div>
                <div className="glass-panel p-4 text-center">
                  <div className="text-3xl font-bold text-blue-400">{report.total_generations}</div>
                  <div className="text-sm text-gray-400">Total Generations</div>
                </div>
                <div className="glass-panel p-4 text-center">
                  <div className="text-3xl font-bold text-purple-400">{report.total_re_rolls}</div>
                  <div className="text-sm text-gray-400">Re-rolls</div>
                </div>
              </div>

              {/* Critique History */}
              <div>
                <h4 className="font-bold mb-3">Critique History</h4>
                <div className="space-y-3">
                  {report.critique_history.map((critique, i) => (
                    <div key={i} className="glass-panel p-4 rounded-lg">
                      <div className="flex items-center justify-between mb-3">
                        <span className="font-medium">Iteration {critique.iteration}</span>
                        <span className={`px-2 py-1 rounded text-sm ${
                          critique.passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                        }`}>
                          {(critique.overall_score * 100).toFixed(1)}%
                        </span>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">{critique.summary}</p>
                      {critique.issues.length > 0 && (
                        <div className="space-y-2">
                          {critique.issues.map((issue, j) => (
                            <div
                              key={j}
                              className={`p-3 rounded text-sm ${
                                issue.severity === 'critical' ? 'bg-red-500/20 border border-red-500/30' :
                                issue.severity === 'major' ? 'bg-yellow-500/20 border border-yellow-500/30' :
                                issue.severity === 'minor' ? 'bg-blue-500/20 border border-blue-500/30' :
                                'bg-gray-700/50 border border-gray-600'
                              }`}
                            >
                              <div className="flex items-start gap-2">
                                <span className="font-medium capitalize">{issue.severity}</span>
                                <span className="text-gray-400">|</span>
                                <span className="text-gray-400 capitalize">{issue.type}</span>
                                <span className="text-gray-400">|</span>
                                <span className="font-mono text-xs">Scene {issue.scene_index + 1}</span>
                              </div>
                              <p className="mt-1 text-gray-300">{issue.description}</p>
                              <p className="mt-1 text-sm text-brand-400">💡 {issue.fix_suggestion}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <div className="text-4xl mb-4">📋</div>
              <p>Complete a director run to see the detailed report</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}