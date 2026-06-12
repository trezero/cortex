/**
 * ConversationList - Sidebar list of conversations with search and create.
 *
 * Displays conversations sorted by updated_at. Each item shows a title,
 * relative time, and a delete button. The active conversation gets a cyan
 * glow highlight.
 */

import { MessageSquare, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "../../../lib/utils";
import type { ChatConversation } from "../types";

interface ConversationListProps {
  conversations: ChatConversation[] | undefined;
  activeId: string | undefined;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

/** Format a date string into a relative time like "2h ago" */
function relativeTime(iso: string): string {
  try {
    const now = Date.now();
    const then = new Date(iso).getTime();
    const diffMs = now - then;
    const diffSec = Math.floor(diffMs / 1000);

    if (diffSec < 60) return "just now";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return "";
  }
}

export function ConversationList({ conversations, activeId, onSelect, onCreate, onDelete }: ConversationListProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filtered = useMemo(() => {
    if (!conversations) return [];
    const sorted = [...conversations].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
    if (!searchQuery.trim()) return sorted;
    const q = searchQuery.toLowerCase();
    return sorted.filter((c) => (c.title ?? "").toLowerCase().includes(q));
  }, [conversations, searchQuery]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 space-y-2 border-b border-white/10">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-300">Conversations</h3>
          <button
            type="button"
            onClick={onCreate}
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-all duration-200",
              "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30",
              "hover:bg-cyan-500/25 hover:border-cyan-500/50 hover:shadow-[0_0_10px_rgba(6,182,212,0.2)]",
            )}
          >
            <Plus className="w-3 h-3" />
            New Chat
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className={cn(
              "w-full pl-8 pr-3 py-1.5 rounded-md text-xs bg-white/5 border border-white/10",
              "text-gray-300 placeholder:text-gray-600 focus:outline-none",
              "focus:border-cyan-500/40 focus:shadow-[0_0_10px_rgba(6,182,212,0.1)]",
              "transition-all duration-200",
            )}
          />
        </div>
      </div>

      {/* Conversation items */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-gray-600">
            <MessageSquare className="w-6 h-6 mb-2" />
            <span className="text-xs">{searchQuery ? "No matches" : "No conversations yet"}</span>
          </div>
        )}

        {filtered.map((conv) => {
          const isActive = conv.id === activeId;
          return (
            <button
              key={conv.id}
              type="button"
              onClick={() => onSelect(conv.id)}
              className={cn(
                "w-full flex items-start gap-2 px-3 py-2.5 text-left transition-all duration-200 group",
                "border-b border-white/5",
                isActive
                  ? "bg-cyan-500/10 border-l-2 border-l-cyan-400 shadow-[inset_0_0_20px_rgba(6,182,212,0.1)]"
                  : "hover:bg-white/5 border-l-2 border-l-transparent",
              )}
            >
              <MessageSquare
                className={cn("w-3.5 h-3.5 mt-0.5 shrink-0", isActive ? "text-cyan-400" : "text-gray-600")}
              />
              <div className="flex-1 min-w-0">
                <div className={cn("text-xs font-medium truncate", isActive ? "text-cyan-200" : "text-gray-300")}>
                  {conv.title || "Untitled"}
                </div>
                <div className="text-[10px] text-gray-600 mt-0.5">
                  {relativeTime(conv.updated_at)}
                </div>
              </div>

              {/* Delete button */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className={cn(
                  "p-1 rounded opacity-0 group-hover:opacity-100 transition-all duration-200",
                  "text-gray-600 hover:text-red-400 hover:bg-red-500/10",
                )}
                aria-label={`Delete ${conv.title}`}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </button>
          );
        })}
      </div>
    </div>
  );
}
