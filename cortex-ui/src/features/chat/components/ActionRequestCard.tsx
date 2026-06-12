/**
 * ActionRequestCard - Highlighted card with approve/deny buttons.
 *
 * Uses amber/orange glow to draw attention when the agent requests
 * a user action (e.g., file write, command execution).
 */

import { AlertTriangle, Check, X } from "lucide-react";
import { cn } from "../../../lib/utils";
import type { ActionRequestEvent } from "../types";

interface ActionRequestCardProps {
  action: ActionRequestEvent;
  onApprove: () => void;
  onDeny: () => void;
}

export function ActionRequestCard({ action, onApprove, onDeny }: ActionRequestCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border my-2 overflow-hidden",
        "backdrop-blur-xl bg-amber-500/5",
        "border-amber-500/50 shadow-[0_0_10px_rgba(245,158,11,0.3)]",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/10 border-b border-amber-500/20">
        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
        <span className="text-xs font-medium text-amber-300">Action Required</span>
        <span className="ml-auto text-[11px] text-amber-400/60 font-mono">{action.action_type}</span>
      </div>

      {/* Description */}
      <div className="px-3 py-2">
        <p className="text-sm text-gray-200">{action.description}</p>

        {/* Payload preview */}
        {Object.keys(action.payload).length > 0 && (
          <pre className="mt-2 text-xs text-gray-400 bg-black/20 rounded p-2 overflow-x-auto max-h-32">
            {JSON.stringify(action.payload, null, 2)}
          </pre>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-amber-500/20">
        <button
          type="button"
          onClick={onApprove}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200",
            "bg-green-500/20 text-green-300 border border-green-500/30",
            "hover:bg-green-500/30 hover:border-green-500/50 hover:shadow-[0_0_10px_rgba(34,197,94,0.2)]",
          )}
        >
          <Check className="w-3.5 h-3.5" />
          Approve
        </button>
        <button
          type="button"
          onClick={onDeny}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200",
            "bg-red-500/20 text-red-300 border border-red-500/30",
            "hover:bg-red-500/30 hover:border-red-500/50 hover:shadow-[0_0_10px_rgba(239,68,68,0.2)]",
          )}
        >
          <X className="w-3.5 h-3.5" />
          Deny
        </button>
      </div>
    </div>
  );
}
