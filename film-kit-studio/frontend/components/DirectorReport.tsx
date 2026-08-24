"use client";

import type { DirectorReport, CritiqueIssue } from '@/lib/types';

interface DirectorReportProps {
  report: DirectorReport | null;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 border-red-500/50 text-red-400',
  major: 'bg-yellow-500/20 border-yellow-500/50 text-yellow-400',
  minor: 'bg-blue-500/20 border-blue-500/50 text-blue-400',
  suggestion: 'bg-gray-700/50 border-gray-600/50 text-gray-300',
};

const ISSUE_TYPE_ICONS: Record<string, string> = {
  continuity: '🔄',
  performance: '🎭',
  technical: '⚙️',
  pacing: '⏱️',
  cinematography: '📷',
  audio: '🔊',
};

export function DirectorReportComponent({ report }: DirectorReportProps) {
  if (!report) {
    return (
      <div className="glass-panel p-8 text-center text-gray-500">
        <div className="text-4xl mb-4">📋</div>
        <p>Complete a director run to see the detailed critique report.</p>
      </div>
    );
  }

  const criticalIssues = report.critique_history.flatMap((c) =>
    c.issues.filter((i) => i.severity === 'critical')
  );
  const majorIssues = report.critique_history.flatMap((c) =>
    c.issues.filter((i) => i.severity === 'major')
  );

  return (
    <div className="glass-panel p-4 space-y-6">
      {/* Summary Header */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white/5 rounded-lg">
          <div className="text-3xl font-bold text-brand-400">{(report.final_score * 100).toFixed(0)}%</div>
          <div className="text-sm text-gray-400">Final Score</div>
        </div>
        <div className="p-4 bg-white/5 rounded-lg">
          <div className="text-3xl font-bold text-green-400">{report.iterations_run}</div>
          <div className="text-sm text-gray-400">Iterations</div>
        </div>
        <div className="p-4 bg-white/5 rounded-lg">
          <div className="text-3xl font-bold text-blue-400">{report.total_generations}</div>
          <div className="text-sm text-gray-400">Generations</div>
        </div>
        <div className="p-4 bg-white/5 rounded-lg">
          <div className="text-3xl font-bold text-orange-400">{report.total_re_rolls}</div>
          <div className="text-sm text-gray-400">Re-rolls</div>
        </div>
      </div>

      {/* Pass/Fail Status */}
      <div className={`p-4 rounded-lg ${report.passed ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${report.passed ? 'bg-green-500' : 'bg-red-500'}`}>
            {report.passed ? '✅' : '❌'}
          </div>
          <div>
            <div className="font-bold text-lg">{report.passed ? 'PASSED' : 'NEEDS MORE WORK'}</div>
            <div className="text-sm text-gray-400">
              {report.passed
                ? 'All scenes meet quality threshold. Ready for final assembly.'
                : `${criticalIssues.length} critical and ${majorIssues.length} major issues remaining.`}
            </div>
          </div>
        </div>
      </div>

      {/* Iteration History */}
      <div className="space-y-4">
        <h3 className="font-bold text-lg flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-brand-500" />
          Iteration History
        </h3>
        <div className="space-y-3">
          {report.critique_history.map((critique, i) => (
            <div
              key={i}
              className={`p-4 rounded-lg ${
                critique.passed ? 'bg-green-500/5 border border-green-500/20' : 'bg-red-500/5 border border-red-500/20'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="px-3 py-1 bg-white/10 rounded-full text-sm font-mono">
                    Iteration {critique.iteration + 1}
                  </span>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    critique.passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                  }`}>
                    {critique.passed ? '✅ PASSED' : '❌ FAILED'}
                  </span>
                  <span className="text-sm text-gray-400">
                    Score: <span className="font-mono font-bold text-brand-400">{(critique.overall_score * 100).toFixed(1)}%</span>
                  </span>
                </div>
                <span className="text-xs text-gray-500">{critique.issues.length} issues</span>
              </div>

              <p className="text-gray-300 text-sm mb-3">{critique.summary}</p>

              {/* Per-scene scores */}
              <div className="flex flex-wrap gap-2">
                {Object.entries(critique.per_scene_scores).map(([sceneIdx, score]) => (
                  <div
                    key={sceneIdx}
                    className={`px-2 py-1 rounded text-xs font-mono ${
                      score >= 0.9 ? 'bg-green-500/20 text-green-400' :
                      score >= 0.8 ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-red-500/20 text-red-400'
                    }`}
                  >
                    Scene {parseInt(sceneIdx) + 1}: {(score * 100).toFixed(0)}%
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* All Issues */}
      <div className="space-y-4">
        <h3 className="font-bold text-lg flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-brand-500" />
          All Issues Found
          <span className="ml-auto text-sm text-gray-400">
            {criticalIssues.length} critical • {majorIssues.length} major
          </span>
        </h3>

        {criticalIssues.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-red-400 mb-2">🔴 Critical Issues (Blockers)</h4>
            {criticalIssues.map((issue, idx) => (
              <div key={idx} className={`p-4 rounded-lg border ${SEVERITY_COLORS.critical}`}>
                <div className="flex items-start gap-3">
                  <span className="text-lg">{ISSUE_TYPE_ICONS[issue.type] || '📋'}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">Scene {issue.scene_index + 1}</span>
                      <span className="text-xs text-gray-400">|</span>
                      <span className="text-xs text-gray-400 capitalize">{issue.type}</span>
                      {issue.timestamp_seconds && (
                        <>
                          <span className="text-xs text-gray-400">|</span>
                          <span className="text-xs text-gray-400 font-mono">
                            @{issue.timestamp_seconds.toFixed(1)}s
                          </span>
                        </>
                      )}
                    </div>
                    <p className="text-gray-300 mb-2">{issue.description}</p>
                    <p className="text-sm text-brand-400 font-medium">💡 Fix: {issue.fix_suggestion}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {majorIssues.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-yellow-400 mb-2">🟡 Major Issues</h4>
            {majorIssues.map((issue, idx) => (
              <div key={idx} className={`p-4 rounded-lg border ${SEVERITY_COLORS.major}`}>
                <div className="flex items-start gap-3">
                  <span className="text-lg">{ISSUE_TYPE_ICONS[issue.type] || '📋'}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">Scene {issue.scene_index + 1}</span>
                      <span className="text-xs text-gray-400">|</span>
                      <span className="text-xs text-gray-400 capitalize">{issue.type}</span>
                    </div>
                    <p className="text-gray-300 mb-2">{issue.description}</p>
                    <p className="text-sm text-brand-400 font-medium">💡 Fix: {issue.fix_suggestion}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Minor + Suggestion issues collapsed */}
        <details className="group">
          <summary className="cursor-pointer flex items-center gap-2 text-gray-400 hover:text-gray-200">
            <span>📋 Minor Issues & Suggestions</span>
            <span className="ml-auto text-sm">Click to expand</span>
          </summary>
          <div className="mt-3 space-y-2">
            {report.critique_history.flatMap((c) =>
              c.issues.filter((i) => i.severity === 'minor' || i.severity === 'suggestion')
            ).map((issue, idx) => (
              <div key={idx} className={`p-3 rounded border ${SEVERITY_COLORS[issue.severity]}`}>
                <div className="flex items-start gap-2">
                  <span className="text-lg">{ISSUE_TYPE_ICONS[issue.type] || '📋'}</span>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm">Scene {issue.scene_index + 1}</span>
                      <span className="text-xs text-gray-500 capitalize">{issue.severity}</span>
                      <span className="text-xs text-gray-500">|</span>
                      <span className="text-xs text-gray-500 capitalize">{issue.type}</span>
                    </div>
                    <p className="text-sm text-gray-300">{issue.description}</p>
                    <p className="text-xs text-brand-400 mt-1">💡 {issue.fix_suggestion}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </details>
      </div>

      {/* Continuity Report */}
      {report.continuity_report && Object.keys(report.continuity_report).length > 0 && (
        <div className="space-y-4 border-t border-white/10 pt-4">
          <h3 className="font-bold text-lg">🔗 Continuity Report</h3>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <h4 className="font-medium text-gray-400 mb-2">Characters</h4>
              <pre className="text-xs text-gray-300 bg-white/5 p-3 rounded overflow-auto max-h-64">
                {JSON.stringify(report.continuity_report.characters || {}, null, 2)}
              </pre>
            </div>
            <div>
              <h4 className="font-medium text-gray-400 mb-2">Locations</h4>
              <pre className="text-xs text-gray-300 bg-white/5 p-3 rounded overflow-auto max-h-64">
                {JSON.stringify(report.continuity_report.locations || {}, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Export Buttons */}
      <div className="flex flex-wrap gap-3 pt-4 border-t border-white/10">
        <a
          href="/api/director/placeholder/edl"
          className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm font-medium transition"
        >
          ⬇️ Download EDL
        </a>
        <a
          href="/api/director/placeholder/fcpxml"
          className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm font-medium transition"
        >
          ⬇️ Download FCPXML
        </a>
        <a
          href="/api/director/placeholder/premiere"
          className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm font-medium transition"
        >
          ⬇️ Download Premiere XML
        </a>
        <a
          href="/api/director/placeholder/davinci"
          className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-sm font-medium transition"
        >
          ⬇️ Download DaVinci DRT
        </a>
      </div>
    </div>
  );
}