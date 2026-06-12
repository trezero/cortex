/**
 * MessageStream - Scrollable container rendering persisted messages and
 * the current streaming message.
 *
 * Auto-scrolls to the bottom on new content. Shows loading and empty states.
 */

import { Loader2, MessageSquare } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "../../../lib/utils";
import type { ChatMessage, StreamingMessage, ToolResultEvent, ToolStartEvent } from "../types";
import { MessageBubble } from "./MessageBubble";
import { ToolUseCard } from "./ToolUseCard";

interface MessageStreamProps {
  messages: ChatMessage[] | undefined;
  isLoading: boolean;
  streamingMessage: StreamingMessage | null;
  toolResults: Map<string, ToolResultEvent>;
  isStreaming: boolean;
}

export function MessageStream({
  messages,
  isLoading,
  streamingMessage,
  toolResults,
  isStreaming,
}: MessageStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages / streaming content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages?.length, streamingMessage?.content, streamingMessage?.tool_calls_in_progress.length]);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-gray-500">
          <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
          <span className="text-sm">Loading messages...</span>
        </div>
      </div>
    );
  }

  // Empty state
  if (!messages || messages.length === 0) {
    if (!streamingMessage) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-gray-500">
            <MessageSquare className="w-8 h-8 text-gray-600" />
            <span className="text-sm">Start a conversation...</span>
          </div>
        </div>
      );
    }
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
      {/* Persisted messages */}
      {messages?.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {/* Streaming tool calls */}
      {streamingMessage?.tool_calls_in_progress.map((toolStart: ToolStartEvent) => (
        <ToolUseCard
          key={toolStart.tool_call_id}
          toolStart={toolStart}
          toolResult={toolResults.get(toolStart.tool_call_id)}
        />
      ))}

      {/* Streaming assistant message */}
      {streamingMessage && streamingMessage.content.length > 0 && (
        <MessageBubble
          message={{
            id: "streaming",
            conversation_id: streamingMessage.conversation_id,
            role: "assistant",
            content: streamingMessage.content,
            tool_calls: null,
            tool_results: null,
            model: null,
            tokens_used: null,
            metadata: null,
            created_at: new Date().toISOString(),
          }}
          isStreaming={isStreaming}
        />
      )}

      {/* Streaming error */}
      {streamingMessage?.error && (
        <div
          className={cn(
            "rounded-lg border px-4 py-3 my-2",
            "bg-red-500/10 border-red-500/30 text-red-300 text-sm",
          )}
        >
          {streamingMessage.error}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
