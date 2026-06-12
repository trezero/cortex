/**
 * ToolUseCard - Collapsible card displaying a tool invocation and its result.
 *
 * Shows tool name and duration in the header; arguments and result are
 * collapsed by default and expand on click.
 */

import { ChevronDown, ChevronRight, Clock, Wrench } from "lucide-react";
import { useState } from "react";
import { cn } from "../../../lib/utils";
import type { ToolResultEvent, ToolStartEvent } from "../types";

interface ToolUseCardProps {
  toolStart: ToolStartEvent;
  toolResult?: ToolResultEvent;
}

/** Format a result value for display */
function formatResult(result: unknown): string {
  if (result === null || result === undefined) return "No result";
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

export function ToolUseCard({ toolStart, toolResult }: ToolUseCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasError = toolResult?.error != null;
  const isComplete = toolResult !== undefined;

  return (
    <div
      className={cn(
        "rounded-lg border transition-all duration-200 my-2",
        "backdrop-blur-xl bg-white/5",
        hasError
          ? "border-red-500/30 shadow-[0_0_10px_rgba(239,68,68,0.15)]"
          : "border-cyan-500/30 shadow-[0_0_10px_rgba(6,182,212,0.2)]",
      )}
    >
      {/* Header - always visible */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-white/5 rounded-lg transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
        )}

        <Wrench className="w-3.5 h-3.5 text-cyan-400 shrink-0" />

        <span className="text-xs font-medium text-cyan-300 truncate">{toolStart.tool_name}</span>

        {/* Status indicator */}
        <span className="ml-auto flex items-center gap-1.5 shrink-0">
          {!isComplete && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />}
          {isComplete && !hasError && <span className="w-1.5 h-1.5 rounded-full bg-green-400" />}
          {hasError && <span className="w-1.5 h-1.5 rounded-full bg-red-400" />}
        </span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-white/5">
          {/* Arguments */}
          <div className="mt-2">
            <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Arguments</div>
            <pre className="text-xs text-gray-300 bg-black/30 rounded p-2 overflow-x-auto max-h-40">
              {JSON.stringify(toolStart.arguments, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {isComplete && (
            <div>
              <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">
                {hasError ? "Error" : "Result"}
              </div>
              <pre
                className={cn(
                  "text-xs rounded p-2 overflow-x-auto max-h-40",
                  hasError ? "text-red-300 bg-red-950/30" : "text-gray-300 bg-black/30",
                )}
              >
                {hasError ? toolResult.error : formatResult(toolResult.result)}
              </pre>
            </div>
          )}

          {/* Duration */}
          {isComplete && (
            <div className="flex items-center gap-1 text-[11px] text-gray-500">
              <Clock className="w-3 h-3" />
              Completed
            </div>
          )}
        </div>
      )}
    </div>
  );
}
