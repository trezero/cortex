import type { RunStatus, WorkflowNode, WorkflowRun } from "../types";

interface WorkflowRunCardProps {
  run: WorkflowRun;
  nodes?: WorkflowNode[];
  onClick?: (runId: string) => void;
}

const STATUS_STYLES: Record<RunStatus, { badge: string; label: string }> = {
  pending: { badge: "bg-gray-500/20 text-gray-400", label: "Pending" },
  dispatched: { badge: "bg-blue-500/20 text-blue-400", label: "Dispatched" },
  running: { badge: "bg-cyan-500/20 text-cyan-400", label: "Running" },
  paused: { badge: "bg-amber-500/20 text-amber-400", label: "Paused" },
  completed: { badge: "bg-green-500/20 text-green-400", label: "Completed" },
  failed: { badge: "bg-red-500/20 text-red-400", label: "Failed" },
  cancelled: { badge: "bg-gray-500/20 text-gray-400", label: "Cancelled" },
};

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function WorkflowRunCard({ run, nodes, onClick }: WorkflowRunCardProps) {
  const status = STATUS_STYLES[run.status];
  const completedCount = nodes?.filter((n) => n.state === "completed").length ?? 0;
  const totalCount = nodes?.length ?? 0;

  return (
    <button
      type="button"
      onClick={() => onClick?.(run.id)}
      className="w-full text-left bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4
        hover:border-cyan-500/30 transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-200 truncate font-mono">
          {run.definition_id.slice(0, 8)}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full ${status.badge}`}>{status.label}</span>
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-500">
        {nodes && (
          <span>
            Nodes: <span className="text-gray-400">{completedCount}/{totalCount}</span>
          </span>
        )}
        <span>
          Started: <span className="text-gray-400">{formatTimestamp(run.started_at)}</span>
        </span>
        {run.completed_at && (
          <span>
            Finished: <span className="text-gray-400">{formatTimestamp(run.completed_at)}</span>
          </span>
        )}
      </div>
    </button>
  );
}
