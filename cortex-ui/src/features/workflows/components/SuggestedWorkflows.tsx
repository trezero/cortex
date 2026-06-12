import { useState } from "react";

import { useAcceptSuggestion, useDismissSuggestion, useSuggestions } from "../hooks/useWorkflowQueries";
import type { DiscoveredPattern } from "../types";

interface SuggestedWorkflowsProps {
  onCustomize?: (pattern: DiscoveredPattern) => void;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  // Interpolate from red (0) through yellow (0.5) to green (1)
  const hue = Math.round(score * 120);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: `hsl(${hue}, 70%, 50%)` }}
        />
      </div>
      <span className="text-xs text-gray-400 tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}

function PatternCard({
  pattern,
  onCustomize,
}: {
  pattern: DiscoveredPattern;
  onCustomize?: (p: DiscoveredPattern) => void;
}) {
  const [yamlOpen, setYamlOpen] = useState(false);
  const [dismissReason, setDismissReason] = useState("");
  const [showDismissInput, setShowDismissInput] = useState(false);

  const accept = useAcceptSuggestion();
  const dismiss = useDismissSuggestion();

  const isActing = accept.isPending || dismiss.isPending;

  function handleAccept() {
    accept.mutate({ id: pattern.id });
  }

  function handleCustomize() {
    onCustomize?.(pattern);
  }

  function handleDismissConfirm() {
    dismiss.mutate({ id: pattern.id, reason: dismissReason || undefined });
    setShowDismissInput(false);
  }

  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-100 truncate">{pattern.pattern_name}</h3>
          {pattern.description && (
            <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{pattern.description}</p>
          )}
        </div>
        <span className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400">
          {pattern.pattern_type}
        </span>
      </div>

      {/* Score */}
      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Confidence score</span>
        </div>
        <ScoreBar score={pattern.final_score} />
      </div>

      {/* Sub-scores */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: "Frequency", value: pattern.frequency_score },
          { label: "Cross-repo", value: pattern.cross_repo_score },
          { label: "Automation", value: pattern.automation_potential },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white/5 rounded p-1.5">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-sm font-medium text-gray-300">{Math.round(value * 100)}%</div>
          </div>
        ))}
      </div>

      {/* Repos involved */}
      {pattern.repos_involved.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {pattern.repos_involved.map((repo) => (
            <span key={repo} className="bg-cyan-500/20 text-cyan-400 text-xs rounded-full px-2 py-0.5">
              {repo}
            </span>
          ))}
        </div>
      )}

      {/* YAML preview (collapsible) */}
      {pattern.suggested_yaml && (
        <div>
          <button
            type="button"
            onClick={() => setYamlOpen((o) => !o)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
          >
            <span>{yamlOpen ? "▼" : "▶"}</span>
            <span>Suggested YAML</span>
          </button>
          {yamlOpen && (
            <pre className="mt-2 text-xs bg-black/30 border border-white/10 rounded p-2 overflow-x-auto text-gray-300 max-h-48 overflow-y-auto">
              {pattern.suggested_yaml}
            </pre>
          )}
        </div>
      )}

      {/* Dismiss reason input */}
      {showDismissInput && (
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Reason (optional)"
            value={dismissReason}
            onChange={(e) => setDismissReason(e.target.value)}
            className="flex-1 text-xs bg-white/5 border border-white/20 rounded px-2 py-1 text-gray-300 placeholder-gray-600
              focus:outline-none focus:border-cyan-500/50"
          />
          <button
            type="button"
            onClick={handleDismissConfirm}
            disabled={isActing}
            className="text-xs px-2 py-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors
              disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Confirm
          </button>
          <button
            type="button"
            onClick={() => setShowDismissInput(false)}
            className="text-xs px-2 py-1 rounded bg-white/5 text-gray-400 hover:bg-white/10 transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Actions */}
      {!showDismissInput && (
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={handleAccept}
            disabled={isActing}
            className="flex-1 text-xs py-1.5 rounded bg-green-500/20 text-green-400 border border-green-500/30
              hover:bg-green-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {accept.isPending ? "Accepting…" : "Accept"}
          </button>
          <button
            type="button"
            onClick={handleCustomize}
            disabled={isActing}
            className="flex-1 text-xs py-1.5 rounded bg-cyan-500/20 text-cyan-400 border border-cyan-500/30
              hover:bg-cyan-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Customize
          </button>
          <button
            type="button"
            onClick={() => setShowDismissInput(true)}
            disabled={isActing}
            className="flex-1 text-xs py-1.5 rounded bg-white/5 text-gray-400 border border-white/10
              hover:bg-white/10 hover:text-red-400 hover:border-red-500/30 transition-colors
              disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}

export function SuggestedWorkflows({ onCustomize }: SuggestedWorkflowsProps) {
  const { data: patterns, isLoading, error } = useSuggestions("pending_review");

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
        Loading suggestions…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12 text-red-400 text-sm">
        Failed to load suggestions: {error instanceof Error ? error.message : "Unknown error"}
      </div>
    );
  }

  if (!patterns || patterns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-500">
        <span className="text-2xl opacity-40">✦</span>
        <p className="text-sm">No workflow suggestions yet.</p>
        <p className="text-xs text-gray-600">Patterns are discovered from your agent activity over time.</p>
      </div>
    );
  }

  const sorted = [...patterns].sort((a, b) => b.final_score - a.final_score);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Suggested Workflows</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {sorted.length} pattern{sorted.length !== 1 ? "s" : ""} discovered from your agent activity
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {sorted.map((pattern) => (
          <PatternCard key={pattern.id} pattern={pattern} onCustomize={onCustomize} />
        ))}
      </div>
    </div>
  );
}
