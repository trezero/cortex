import { useApprovals } from "../hooks/useWorkflowQueries";
import type { ApprovalRequest } from "../types";

interface ApprovalListProps {
  onSelect: (id: string) => void;
  selectedId?: string;
}

const STATUS_BADGE: Record<ApprovalRequest["status"], string> = {
  pending: "bg-amber-500/20 text-amber-400",
  approved: "bg-green-500/20 text-green-400",
  rejected: "bg-red-500/20 text-red-400",
  expired: "bg-gray-500/20 text-gray-400",
};

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ApprovalList({ onSelect, selectedId }: ApprovalListProps) {
  const { data: approvals, isLoading, error } = useApprovals("pending");

  if (isLoading) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-gray-400 text-sm">Loading approvals...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-red-400 text-sm">
          Failed to load approvals: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      </div>
    );
  }

  if (!approvals?.length) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-gray-500 text-sm text-center">No pending approvals</div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-white/10">
        <h3 className="text-sm font-semibold text-gray-200">
          Pending Approvals
          <span className="ml-2 text-xs text-cyan-400">({approvals.length})</span>
        </h3>
      </div>
      <div className="divide-y divide-white/5">
        {approvals.map((approval) => (
          <button
            key={approval.id}
            type="button"
            onClick={() => onSelect(approval.id)}
            className={`w-full text-left px-4 py-3 transition-colors hover:bg-white/5 ${
              selectedId === approval.id ? "bg-white/10 border-l-2 border-l-cyan-500" : ""
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-gray-200 truncate">
                {approval.yaml_node_id}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_BADGE[approval.status]}`}>
                {approval.status}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span>{approval.approval_type}</span>
              <span>&middot;</span>
              <span>{formatTimestamp(approval.created_at)}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
