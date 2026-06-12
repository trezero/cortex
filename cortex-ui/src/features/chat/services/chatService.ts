/**
 * Chat Service
 *
 * REST calls to the Main Server (/api/chat/*) use callAPIWithETag.
 * SSE streaming to the Agent Service (/agents/chat/stream) uses raw fetch
 * so the caller can consume the event stream incrementally.
 */

import { callAPIWithETag } from "../../shared/api/apiClient";
import type {
  AnySSEEvent,
  ChatConversation,
  ChatMessage,
  CreateConversationRequest,
  SendMessageRequest,
  UpdateConversationRequest,
  UserProfile,
} from "../types";

export const chatService = {
  // ─── Conversations ────────────────────────────────────────────────────────

  async listConversations(): Promise<ChatConversation[]> {
    const response = await callAPIWithETag<{ conversations: ChatConversation[] }>("/api/chat/conversations");
    return response.conversations ?? [];
  },

  async createConversation(data: CreateConversationRequest): Promise<ChatConversation> {
    return callAPIWithETag<ChatConversation>("/api/chat/conversations", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getConversation(conversationId: string): Promise<ChatConversation> {
    return callAPIWithETag<ChatConversation>(`/api/chat/conversations/${conversationId}`);
  },

  async updateConversation(conversationId: string, data: UpdateConversationRequest): Promise<ChatConversation> {
    return callAPIWithETag<ChatConversation>(`/api/chat/conversations/${conversationId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async deleteConversation(conversationId: string): Promise<void> {
    await callAPIWithETag(`/api/chat/conversations/${conversationId}`, {
      method: "DELETE",
    });
  },

  // ─── Messages ─────────────────────────────────────────────────────────────

  async getMessages(conversationId: string): Promise<ChatMessage[]> {
    const response = await callAPIWithETag<{ messages: ChatMessage[] }>(
      `/api/chat/conversations/${conversationId}/messages`,
    );
    return response.messages ?? [];
  },

  async searchMessages(query: string): Promise<ChatMessage[]> {
    const params = new URLSearchParams({ q: query });
    const response = await callAPIWithETag<{ messages: ChatMessage[] }>(
      `/api/chat/messages/search?${params.toString()}`,
    );
    return response.messages ?? [];
  },

  // ─── User Profile ─────────────────────────────────────────────────────────

  async getProfile(): Promise<UserProfile> {
    const response = await callAPIWithETag<{ profile: UserProfile }>("/api/chat/profile");
    return response.profile;
  },

  async updateProfile(data: Partial<UserProfile>): Promise<UserProfile> {
    const response = await callAPIWithETag<{ profile: UserProfile }>("/api/chat/profile", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    return response.profile;
  },

  // ─── Categories ───────────────────────────────────────────────────────────

  async listCategories(): Promise<string[]> {
    const response = await callAPIWithETag<{ categories: string[] }>("/api/chat/categories");
    return response.categories ?? [];
  },

  // ─── SSE Streaming ────────────────────────────────────────────────────────

  /**
   * Stream a message from the Agent Service via SSE.
   *
   * Returns an AbortController so the caller can cancel the stream.
   * Events are delivered one at a time to `onEvent`; errors to `onError`.
   */
  streamMessage(
    data: SendMessageRequest,
    onEvent: (event: AnySSEEvent) => void,
    onError: (error: Error) => void,
  ): AbortController {
    const controller = new AbortController();

    (async () => {
      try {
        const response = await fetch("/agents/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
          signal: controller.signal,
        });

        if (!response.ok) {
          let detail = `HTTP ${response.status}`;
          try {
            const body = await response.text();
            if (body) detail = body;
          } catch {
            // ignore body parse failure
          }
          throw new Error(`Agent stream failed: ${detail}`);
        }

        if (!response.body) {
          throw new Error("Agent stream returned no body");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process all complete SSE messages in the buffer
          const lines = buffer.split("\n");
          // Keep the last (potentially incomplete) line in the buffer
          buffer = lines.pop() ?? "";

          let eventData = "";
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              eventData += line.slice(6);
            } else if (line === "") {
              // Blank line = end of SSE message
              if (eventData) {
                try {
                  const parsed = JSON.parse(eventData) as AnySSEEvent;
                  onEvent(parsed);
                } catch (parseError) {
                  console.error("Failed to parse SSE event:", eventData, parseError);
                }
                eventData = "";
              }
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          // Intentional cancellation — not an error
          return;
        }
        onError(error instanceof Error ? error : new Error("Unknown streaming error"));
      }
    })();

    return controller;
  },

  // ─── Agent Health ─────────────────────────────────────────────────────────

  /**
   * Check if the Agent Service is reachable.
   * Returns false on any error rather than throwing.
   */
  async checkAgentHealth(): Promise<boolean> {
    try {
      const response = await fetch("/agents/health", {
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch {
      return false;
    }
  },

  // ─── Action Confirmation ──────────────────────────────────────────────────

  async confirmAction(actionId: string): Promise<void> {
    await callAPIWithETag(`/api/chat/actions/${actionId}/confirm`, {
      method: "POST",
    });
  },

  async denyAction(actionId: string): Promise<void> {
    await callAPIWithETag(`/api/chat/actions/${actionId}/deny`, {
      method: "POST",
    });
  },
};
