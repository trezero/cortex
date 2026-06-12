import { useState } from "react";

import { useResolveApproval } from "../hooks/useWorkflowQueries";

interface ApprovalActionsProps {
  approvalId: string;
}

export function ApprovalActions({ approvalId }: ApprovalActionsProps) {
  const [comment, setComment] = useState("");
  const resolveApproval = useResolveApproval();
  const isSubmitting = resolveApproval.isPending;

  function handleResolve(decision: "approved" | "rejected") {
    resolveApproval.mutate({
      id: approvalId,
      data: {
        decision,
        comment: comment.trim() || undefined,
      },
    });
  }

  return (
    <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4 space-y-3">
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional comment..."
        rows={2}
        disabled={isSubmitting}
        className="w-full bg-black/30 border border-white/10 rounded-md px-3 py-2 text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-cyan-500/50 disabled:opacity-50"
      />
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => handleResolve("approved")}
          disabled={isSubmitting}
          className="flex-1 px-4 py-2 rounded-md text-sm font-medium text-white bg-cyan-600 hover:bg-cyan-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting ? "Submitting..." : "Approve"}
        </button>
        <button
          type="button"
          onClick={() => handleResolve("rejected")}
          disabled={isSubmitting}
          className="flex-1 px-4 py-2 rounded-md text-sm font-medium text-white bg-red-600/80 hover:bg-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting ? "Submitting..." : "Reject"}
        </button>
      </div>
      {resolveApproval.isError && (
        <div className="text-sm text-red-400">
          Failed to resolve: {resolveApproval.error instanceof Error ? resolveApproval.error.message : "Unknown error"}
        </div>
      )}
    </div>
  );
}
