/**
 * ConversationContext - Right collapsible panel showing conversation metadata.
 *
 * Displays project scope, action mode toggle, model selector,
 * and conversation metadata (created, message count, category).
 */

import { ChevronRight, FolderOpen, Info, Clock } from "lucide-react";
import { cn } from "../../../lib/utils";
import type { ChatConversation } from "../types";
import { useMessages } from "../hooks/useChatQueries";
import { ModelSelector } from "./ModelSelector";

interface ConversationContextProps {
  conversation: ChatConversation | undefined;
  isOpen: boolean;
  onToggle: () => void;
  model: string;
  onModelChange: (model: string) => void;
  actionMode: boolean;
  onActionModeChange: (enabled: boolean) => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function ConversationContext({
  conversation,
  isOpen,
  onToggle,
  model,
  onModelChange,
  actionMode,
  onActionModeChange,
}: ConversationContextProps) {
  const { data: messages } = useMessages(conversation?.id);
  const messageCount = messages?.length ?? 0;

  return (
    <div
      className={cn(
        "border-l border-white/10 transition-all duration-300 flex flex-col",
        isOpen ? "w-[260px]" : "w-10",
      )}
    >
      {/* Toggle button */}
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center justify-center h-12 border-b border-white/10 hover:bg-white/5 transition-colors"
      >
        <ChevronRight
          className={cn("w-4 h-4 text-gray-500 transition-transform duration-300", isOpen && "rotate-180")}
        />
      </button>

      {isOpen && (
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {conversation ? (
            <>
              {/* Title */}
              <div>
                <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Conversation</div>
                <div className="text-sm text-gray-200 font-medium">{conversation.title || "Untitled"}</div>
              </div>

              {/* Project scope */}
              {conversation.project_id && (
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <FolderOpen className="w-3.5 h-3.5" />
                  <span className="truncate">{conversation.project_id}</span>
                </div>
              )}

              {/* Created */}
              {conversation.created_at && (
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{formatDate(conversation.created_at)}</span>
                </div>
              )}

              {/* Message count */}
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <Info className="w-3.5 h-3.5" />
                <span>{messageCount} messages</span>
              </div>

              {/* Divider */}
              <div className="h-px bg-white/10" />

              {/* Model */}
              <div>
                <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Model</div>
                <ModelSelector value={model} onChange={onModelChange} />
              </div>

              {/* Action mode */}
              <div>
                <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Action Mode</div>
                <button
                  type="button"
                  onClick={() => onActionModeChange(!actionMode)}
                  className={cn(
                    "flex items-center gap-2 w-full px-3 py-2 rounded-md text-xs transition-all duration-200",
                    actionMode
                      ? "bg-amber-500/15 border border-amber-500/30 text-amber-300"
                      : "bg-white/5 border border-white/10 text-gray-400 hover:text-gray-300",
                  )}
                >
                  <div
                    className={cn(
                      "w-6 h-3.5 rounded-full flex items-center transition-all duration-200 px-0.5",
                      actionMode ? "bg-amber-500/40 justify-end" : "bg-gray-700 justify-start",
                    )}
                  >
                    <div
                      className={cn(
                        "w-2.5 h-2.5 rounded-full transition-colors duration-200",
                        actionMode ? "bg-amber-400" : "bg-gray-500",
                      )}
                    />
                  </div>
                  <span>{actionMode ? "Requires approval" : "Auto-approve"}</span>
                </button>
              </div>
            </>
          ) : (
            <div className="text-xs text-gray-600 text-center pt-8">Select a conversation to view details</div>
          )}
        </div>
      )}
    </div>
  );
}
