import { A2UIDisplay } from "../../generative-ui/components/A2UIDisplay";
import { useApprovalDetail } from "../hooks/useWorkflowQueries";
import type { ApprovalRequest } from "../types";
import { ApprovalActions } from "./ApprovalActions";

interface ApprovalDetailProps {
  approvalId: string;
}

const STATUS_BADGE: Record<ApprovalRequest["status"], string> = {
  pending: "bg-amber-500/20 text-amber-400",
  approved: "bg-green-500/20 text-green-400",
  rejected: "bg-red-500/20 text-red-400",
  expired: "bg-gray-500/20 text-gray-400",
};

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function ApprovalDetail({ approvalId }: ApprovalDetailProps) {
  const { data: approval, isLoading, error } = useApprovalDetail(approvalId);

  if (isLoading) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-gray-400 text-sm">Loading approval details...</div>
      </div>
    );
  }

  if (error || !approval) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-red-400 text-sm">
          {error instanceof Error ? error.message : "Approval not found"}
        </div>
      </div>
    );
  }

  const hasComponents = approval.payload.components && approval.payload.components.length > 0;
  const hasRawOutput = !!approval.payload.raw_output;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-base font-semibold text-gray-200">{approval.yaml_node_id}</h3>
          <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_BADGE[approval.status]}`}>
            {approval.status}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>Type: <span className="text-gray-400">{approval.approval_type}</span></span>
          <span>Created: <span className="text-gray-400">{formatTimestamp(approval.created_at)}</span></span>
          <span>Run: <span className="text-gray-400 font-mono">{approval.workflow_run_id.slice(0, 8)}</span></span>
        </div>
      </div>

      {/* A2UI component payload */}
      {hasComponents && <A2UIDisplay components={approval.payload.components!} />}

      {/* Raw output fallback */}
      {!hasComponents && hasRawOutput && (
        <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4">
          <pre className="text-sm text-gray-300 font-mono whitespace-pre-wrap break-words">
            {approval.payload.raw_output}
          </pre>
        </div>
      )}

      {/* No payload */}
      {!hasComponents && !hasRawOutput && (
        <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4">
          <p className="text-sm text-gray-500 italic">No payload content available</p>
        </div>
      )}

      {/* Approval actions (only for pending) */}
      {approval.status === "pending" && <ApprovalActions approvalId={approval.id} />}

      {/* Resolution info (for resolved approvals) */}
      {approval.resolved_at && (
        <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-400 mb-2">Resolution</h4>
          <div className="space-y-1 text-sm">
            <div className="text-gray-300">
              <span className="text-gray-500">Resolved by:</span>{" "}
              {approval.resolved_by ?? "Unknown"}
            </div>
            {approval.resolved_via && (
              <div className="text-gray-300">
                <span className="text-gray-500">Via:</span> {approval.resolved_via}
              </div>
            )}
            {approval.resolved_comment && (
              <div className="text-gray-300">
                <span className="text-gray-500">Comment:</span> {approval.resolved_comment}
              </div>
            )}
            <div className="text-gray-300">
              <span className="text-gray-500">Resolved at:</span>{" "}
              {formatTimestamp(approval.resolved_at)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
