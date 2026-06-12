import { useCallback, useEffect, useRef, useState } from "react";

import { useWorkflowRun } from "../hooks/useWorkflowQueries";
import type { NodeState, RunStatus, WorkflowNode, WorkflowRun, WorkflowSSEEvent } from "../types";

interface WorkflowRunViewProps {
  runId: string;
  onBack?: () => void;
  onApprovalClick?: (approvalId: string) => void;
}

// -- Status / node-state styling ------------------------------------------------

const RUN_STATUS_STYLES: Record<RunStatus, { badge: string; label: string }> = {
  pending: { badge: "bg-gray-500/20 text-gray-400", label: "Pending" },
  dispatched: { badge: "bg-blue-500/20 text-blue-400", label: "Dispatched" },
  running: { badge: "bg-cyan-500/20 text-cyan-400", label: "Running" },
  paused: { badge: "bg-amber-500/20 text-amber-400", label: "Paused" },
  completed: { badge: "bg-green-500/20 text-green-400", label: "Completed" },
  failed: { badge: "bg-red-500/20 text-red-400", label: "Failed" },
  cancelled: { badge: "bg-gray-500/20 text-gray-400", label: "Cancelled" },
};

const NODE_STATE_DOT: Record<NodeState, string> = {
  pending: "bg-gray-500",
  running: "bg-cyan-500 animate-pulse",
  waiting_approval: "bg-amber-500 animate-pulse",
  completed: "bg-green-500",
  failed: "bg-red-500",
  skipped: "bg-gray-400",
  cancelled: "bg-gray-400",
};

// -- Helpers ------------------------------------------------------------------

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface ProgressMessage {
  nodeId: string;
  message: string;
  timestamp: string;
}

interface PendingApproval {
  approvalId: string;
  nodeId: string;
  yamlNodeId: string;
  timestamp: string;
}

// -- Component ----------------------------------------------------------------

export function WorkflowRunView({ runId, onBack, onApprovalClick }: WorkflowRunViewProps) {
  const { data, isLoading, error } = useWorkflowRun(runId);

  // Local SSE-driven state, seeded from the query once available
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [nodes, setNodes] = useState<WorkflowNode[]>([]);
  const [progressMessages, setProgressMessages] = useState<ProgressMessage[]>([]);
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [sseConnected, setSseConnected] = useState(false);

  const seededRef = useRef(false);
  const progressEndRef = useRef<HTMLDivElement>(null);

  // Seed local state from the initial query response
  useEffect(() => {
    if (data && !seededRef.current) {
      setRunStatus(data.run.status);
      setNodes(data.nodes);
      seededRef.current = true;
    }
  }, [data]);

  // Auto-scroll progress feed
  useEffect(() => {
    progressEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [progressMessages]);

  // -- SSE connection ---------------------------------------------------------

  const handleSSEEvent = useCallback((event: WorkflowSSEEvent) => {
    const d = event.data;

    switch (event.type) {
      case "node_state_changed": {
        const nodeId = d.node_id as string;
        const newState = d.state as NodeState;
        const output = (d.output as string | null) ?? null;
        const err = (d.error as string | null) ?? null;
        const startedAt = (d.started_at as string | null) ?? null;
        const completedAt = (d.completed_at as string | null) ?? null;

        setNodes((prev) =>
          prev.map((n) =>
            n.node_id === nodeId
              ? { ...n, state: newState, output, error: err, started_at: startedAt ?? n.started_at, completed_at: completedAt ?? n.completed_at }
              : n,
          ),
        );
        break;
      }

      case "run_status_changed": {
        setRunStatus(d.status as RunStatus);
        break;
      }

      case "approval_requested": {
        setApprovals((prev) => [
          ...prev,
          {
            approvalId: d.approval_id as string,
            nodeId: d.node_id as string,
            yamlNodeId: (d.yaml_node_id as string) ?? (d.node_id as string),
            timestamp: (d.timestamp as string) ?? new Date().toISOString(),
          },
        ]);
        break;
      }

      case "node_progress": {
        setProgressMessages((prev) => [
          ...prev,
          {
            nodeId: (d.node_id as string) ?? "system",
            message: (d.message as string) ?? JSON.stringify(d),
            timestamp: (d.timestamp as string) ?? new Date().toISOString(),
          },
        ]);
        break;
      }

      default:
        break;
    }
  }, []);

  useEffect(() => {
    if (!runId) return;

    const eventSource = new EventSource(`/api/workflows/${runId}/events`);

    eventSource.onopen = () => setSseConnected(true);

    eventSource.onmessage = (event) => {
      try {
        const parsed: WorkflowSSEEvent = JSON.parse(event.data);
        handleSSEEvent(parsed);
      } catch {
        // Ignore malformed events
      }
    };

    eventSource.onerror = () => {
      setSseConnected(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
      setSseConnected(false);
    };
  }, [runId, handleSSEEvent]);

  // -- Render helpers ---------------------------------------------------------

  const currentRun: WorkflowRun | null = data?.run ?? null;
  const displayStatus = runStatus ?? currentRun?.status ?? "pending";
  const statusStyle = RUN_STATUS_STYLES[displayStatus];

  // -- Loading / Error --------------------------------------------------------

  if (isLoading && !seededRef.current) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-gray-400 text-sm">Loading workflow run...</div>
      </div>
    );
  }

  if (error && !seededRef.current) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-red-400 text-sm">
          Failed to load run: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      </div>
    );
  }

  // -- Main view --------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {onBack && (
              <button
                type="button"
                onClick={onBack}
                className="text-gray-400 hover:text-gray-200 transition-colors text-sm"
              >
                &larr; Back
              </button>
            )}
            <h2 className="text-base font-semibold text-gray-200">
              Run <span className="font-mono text-cyan-400">{runId.slice(0, 8)}</span>
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`inline-block w-2 h-2 rounded-full ${sseConnected ? "bg-green-500" : "bg-red-500"}`}
              title={sseConnected ? "SSE connected" : "SSE disconnected"}
            />
            <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyle.badge}`}>
              {statusStyle.label}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
          {currentRun && (
            <>
              <span>
                Definition: <span className="text-gray-400 font-mono">{currentRun.definition_id.slice(0, 8)}</span>
              </span>
              <span>
                Started: <span className="text-gray-400">{formatTimestamp(currentRun.started_at)}</span>
              </span>
              {currentRun.completed_at && (
                <span>
                  Completed: <span className="text-gray-400">{formatTimestamp(currentRun.completed_at)}</span>
                </span>
              )}
              {currentRun.triggered_by && (
                <span>
                  Triggered by: <span className="text-gray-400">{currentRun.triggered_by}</span>
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Node state list */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10">
          <h3 className="text-sm font-semibold text-gray-200">
            Nodes
            <span className="ml-2 text-xs text-cyan-400">
              ({nodes.filter((n) => n.state === "completed").length}/{nodes.length})
            </span>
          </h3>
        </div>

        {nodes.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-gray-500">No nodes recorded yet</div>
        ) : (
          <div className="divide-y divide-white/5">
            {nodes.map((node) => (
              <div key={node.id} className="px-4 py-3 flex items-start gap-3">
                {/* State indicator dot */}
                <span
                  className={`mt-1 inline-block w-2.5 h-2.5 rounded-full shrink-0 ${NODE_STATE_DOT[node.state]}`}
                  title={node.state}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-sm font-medium text-gray-200 truncate">{node.node_id}</span>
                    <span className="text-xs text-gray-500 capitalize">{node.state.replace("_", " ")}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-3 text-xs text-gray-500">
                    {node.started_at && <span>Started: {formatTimestamp(node.started_at)}</span>}
                    {node.completed_at && <span>Finished: {formatTimestamp(node.completed_at)}</span>}
                  </div>
                  {node.output && (
                    <pre className="mt-1 text-xs text-gray-400 font-mono whitespace-pre-wrap break-words line-clamp-3">
                      {node.output}
                    </pre>
                  )}
                  {node.error && (
                    <p className="mt-1 text-xs text-red-400 break-words">{node.error}</p>
                  )}
                  {node.state === "waiting_approval" && (
                    <span className="mt-1 inline-block text-xs text-amber-400">
                      Awaiting approval
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pending approvals */}
      {approvals.length > 0 && (
        <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-white/10">
            <h3 className="text-sm font-semibold text-gray-200">
              Approval Requests
              <span className="ml-2 text-xs text-amber-400">({approvals.length})</span>
            </h3>
          </div>
          <div className="divide-y divide-white/5">
            {approvals.map((a) => (
              <div key={a.approvalId} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <span className="text-sm text-gray-200">{a.yamlNodeId}</span>
                  <span className="ml-2 text-xs text-gray-500">{formatTimestamp(a.timestamp)}</span>
                </div>
                {onApprovalClick && (
                  <button
                    type="button"
                    onClick={() => onApprovalClick(a.approvalId)}
                    className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    Review
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Progress feed */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10">
          <h3 className="text-sm font-semibold text-gray-200">
            Progress
            <span className="ml-2 text-xs text-gray-500">({progressMessages.length})</span>
          </h3>
        </div>
        <div className="max-h-64 overflow-y-auto">
          {progressMessages.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-gray-500">
              No progress messages yet
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {progressMessages.map((msg, idx) => (
                <div key={`${msg.timestamp}-${idx}`} className="px-4 py-2 text-xs">
                  <span className="text-gray-500 font-mono mr-2">{msg.nodeId}</span>
                  <span className="text-gray-300">{msg.message}</span>
                  <span className="ml-2 text-gray-600">{formatTimestamp(msg.timestamp)}</span>
                </div>
              ))}
              <div ref={progressEndRef} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
