/**
 * useSSEStream - Custom hook wrapping chatService.streamMessage().
 *
 * Manages StreamingMessage state: accumulates text deltas and tool calls,
 * and on message_complete appends the finalized message to the TanStack
 * Query cache so the persisted message list stays in sync.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { chatService } from "../services/chatService";
import type {
  AnySSEEvent,
  ChatMessage,
  StreamingMessage,
  ToolStartEvent,
  ToolResultEvent,
} from "../types";
import { chatKeys } from "./useChatQueries";

interface UseSSEStreamReturn {
  streamingMessage: StreamingMessage | null;
  toolResults: Map<string, ToolResultEvent>;
  isStreaming: boolean;
  sendMessage: (conversationId: string, content: string, model?: string) => void;
  cancelStream: () => void;
}

function createEmptyStreamingMessage(conversationId: string): StreamingMessage {
  return {
    conversation_id: conversationId,
    content: "",
    tool_calls_in_progress: [],
    is_complete: false,
    error: null,
  };
}

export function useSSEStream(): UseSSEStreamReturn {
  const queryClient = useQueryClient();
  const [streamingMessage, setStreamingMessage] = useState<StreamingMessage | null>(null);
  const [toolResults, setToolResults] = useState<Map<string, ToolResultEvent>>(new Map());
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const accumulatedContentRef = useRef("");

  const cancelStream = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    accumulatedContentRef.current = "";
    setIsStreaming(false);
    setStreamingMessage(null);
    setToolResults(new Map());
  }, []);

  const sendMessage = useCallback(
    (conversationId: string, content: string, model?: string) => {
      // Cancel any in-flight stream
      controllerRef.current?.abort();

      setStreamingMessage(createEmptyStreamingMessage(conversationId));
      setToolResults(new Map());
      setIsStreaming(true);
      accumulatedContentRef.current = "";

      // Optimistically add the user message to the cache
      const optimisticUserMessage: ChatMessage = {
        id: `temp-user-${Date.now()}`,
        conversation_id: conversationId,
        role: "user",
        content,
        tool_calls: null,
        tool_results: null,
        model: null,
        tokens_used: null,
        metadata: null,
        created_at: new Date().toISOString(),
      };

      queryClient.setQueryData(chatKeys.messages(conversationId), (old: ChatMessage[] | undefined) =>
        old ? [...old, optimisticUserMessage] : [optimisticUserMessage],
      );

      const handleEvent = (event: AnySSEEvent) => {
        switch (event.type) {
          case "text_delta":
            accumulatedContentRef.current += event.delta;
            setStreamingMessage((prev) =>
              prev ? { ...prev, content: prev.content + event.delta } : prev,
            );
            break;

          case "tool_start":
            setStreamingMessage((prev) =>
              prev
                ? {
                    ...prev,
                    tool_calls_in_progress: [...prev.tool_calls_in_progress, event as ToolStartEvent],
                  }
                : prev,
            );
            break;

          case "tool_result": {
            const toolResultEvent = event as ToolResultEvent;
            setToolResults((prev) => {
              const next = new Map(prev);
              next.set(toolResultEvent.tool_call_id, toolResultEvent);
              return next;
            });
            break;
          }

          case "message_complete": {
            // Build the finalized assistant message using accumulated streaming content
            const finalMessage: ChatMessage = {
              id: event.message_id || `assistant-${Date.now()}`,
              conversation_id: conversationId,
              role: "assistant",
              content: accumulatedContentRef.current,
              tool_calls: null,
              tool_results: null,
              model: model ?? null,
              tokens_used: event.tokens_used,
              metadata: null,
              created_at: new Date().toISOString(),
            };

            queryClient.setQueryData(
              chatKeys.messages(conversationId),
              (old: ChatMessage[] | undefined) => (old ? [...old, finalMessage] : [finalMessage]),
            );

            // Also invalidate conversation list to update updated_at ordering
            queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });

            setStreamingMessage(null);
            setToolResults(new Map());
            setIsStreaming(false);
            controllerRef.current = null;
            break;
          }

          case "action_request":
            // Handled by streaming message state; UI renders ActionRequestCard
            break;

          case "error":
            setStreamingMessage((prev) =>
              prev ? { ...prev, error: event.error, is_complete: true } : prev,
            );
            setIsStreaming(false);
            controllerRef.current = null;
            break;
        }
      };

      const handleError = (error: Error) => {
        setStreamingMessage((prev) =>
          prev ? { ...prev, error: error.message, is_complete: true } : prev,
        );
        setIsStreaming(false);
        controllerRef.current = null;
      };

      // Build conversation history from cached messages for context
      const cachedMessages: ChatMessage[] = queryClient.getQueryData(chatKeys.messages(conversationId)) || [];
      const conversationHistory = cachedMessages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content || "" }));

      controllerRef.current = chatService.streamMessage(
        {
          conversation_id: conversationId,
          content,
          model,
          conversation_history: conversationHistory,
        },
        handleEvent,
        handleError,
      );
    },
    [queryClient],
  );

  return {
    streamingMessage,
    toolResults,
    isStreaming,
    sendMessage,
    cancelStream,
  };
}
