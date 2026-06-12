/**
 * TanStack Query hooks for the chat feature.
 *
 * Message queries use STALE_TIMES.static because the SSE stream is the
 * authoritative source for new content — polling would be redundant.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "../../shared/config/queryPatterns";
import { chatService } from "../services/chatService";
import type {
  ChatConversation,
  CreateConversationRequest,
  SendMessageRequest,
  UpdateConversationRequest,
  UserProfile,
} from "../types";

// ─── Query Key Factory ─────────────────────────────────────────────────────

export const chatKeys = {
  all: ["chat"] as const,
  conversations: () => [...chatKeys.all, "conversations"] as const,
  conversationDetail: (id: string) => [...chatKeys.all, "conversations", "detail", id] as const,
  messages: (conversationId: string) => [...chatKeys.all, "messages", conversationId] as const,
  profile: () => [...chatKeys.all, "profile"] as const,
  categories: () => [...chatKeys.all, "categories"] as const,
  search: (query: string) => [...chatKeys.all, "search", query] as const,
  agentHealth: () => [...chatKeys.all, "agentHealth"] as const,
};

// ─── Conversation Queries ──────────────────────────────────────────────────

export function useConversations() {
  return useQuery<ChatConversation[]>({
    queryKey: chatKeys.conversations(),
    queryFn: () => chatService.listConversations(),
    staleTime: STALE_TIMES.normal,
  });
}

export function useConversationDetail(conversationId: string | undefined) {
  return useQuery<ChatConversation>({
    queryKey: conversationId ? chatKeys.conversationDetail(conversationId) : DISABLED_QUERY_KEY,
    queryFn: () =>
      conversationId
        ? chatService.getConversation(conversationId)
        : Promise.reject(new Error("No conversation ID provided")),
    enabled: !!conversationId,
    staleTime: STALE_TIMES.normal,
  });
}

// ─── Conversation Mutations ────────────────────────────────────────────────

export function useCreateConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateConversationRequest) => chatService.createConversation(data),
    onSuccess: (newConversation) => {
      // Prepend to list without full refetch
      queryClient.setQueryData(chatKeys.conversations(), (old: ChatConversation[] | undefined) =>
        old ? [newConversation, ...old] : [newConversation],
      );
      // Seed detail cache
      queryClient.setQueryData(chatKeys.conversationDetail(newConversation.id), newConversation);
    },
    onError: (error) => {
      console.error("Failed to create conversation:", error);
    },
  });
}

export function useUpdateConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ conversationId, data }: { conversationId: string; data: UpdateConversationRequest }) =>
      chatService.updateConversation(conversationId, data),
    onSuccess: (updated) => {
      // Update detail cache
      queryClient.setQueryData(chatKeys.conversationDetail(updated.id), updated);
      // Update list cache entry
      queryClient.setQueryData(chatKeys.conversations(), (old: ChatConversation[] | undefined) =>
        old ? old.map((c) => (c.id === updated.id ? updated : c)) : [updated],
      );
    },
    onError: (error) => {
      console.error("Failed to update conversation:", error);
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (conversationId: string) => chatService.deleteConversation(conversationId),
    onSuccess: (_void, conversationId) => {
      // Remove from list
      queryClient.setQueryData(chatKeys.conversations(), (old: ChatConversation[] | undefined) =>
        old ? old.filter((c) => c.id !== conversationId) : [],
      );
      // Remove detail and messages caches
      queryClient.removeQueries({ queryKey: chatKeys.conversationDetail(conversationId) });
      queryClient.removeQueries({ queryKey: chatKeys.messages(conversationId) });
    },
    onError: (error) => {
      console.error("Failed to delete conversation:", error);
    },
  });
}

// ─── Message Queries ───────────────────────────────────────────────────────

/**
 * Fetches the persisted messages for a conversation.
 * staleTime is static because live updates arrive via SSE, not polling.
 */
export function useMessages(conversationId: string | undefined) {
  return useQuery({
    queryKey: conversationId ? chatKeys.messages(conversationId) : DISABLED_QUERY_KEY,
    queryFn: () =>
      conversationId
        ? chatService.getMessages(conversationId)
        : Promise.reject(new Error("No conversation ID provided")),
    enabled: !!conversationId,
    staleTime: STALE_TIMES.static,
  });
}

export function useSearchMessages(query: string) {
  return useQuery({
    queryKey: query ? chatKeys.search(query) : DISABLED_QUERY_KEY,
    queryFn: () => (query ? chatService.searchMessages(query) : Promise.reject(new Error("No query provided"))),
    enabled: !!query,
    staleTime: STALE_TIMES.normal,
  });
}

// ─── Stream Mutation ──────────────────────────────────────────────────────

/**
 * Fires a streaming message request. The returned mutation does not store
 * data in the query cache directly — callers append SSE events to local
 * state and then invalidate the messages query when the stream completes.
 */
export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      data,
      onEvent,
      onError,
    }: {
      data: SendMessageRequest;
      onEvent: Parameters<typeof chatService.streamMessage>[1];
      onError: Parameters<typeof chatService.streamMessage>[2];
    }) => {
      // streamMessage is fire-and-forget; we wrap it in a Promise that
      // resolves immediately so useMutation can track loading state.
      const controller = chatService.streamMessage(data, onEvent, onError);
      // Return the AbortController so callers can cancel via mutation.data
      return Promise.resolve(controller);
    },
    onSettled: (_controller, _error, variables) => {
      // Invalidate persisted messages so the cache refreshes after streaming
      queryClient.invalidateQueries({ queryKey: chatKeys.messages(variables.data.conversation_id) });
    },
  });
}

// ─── Profile Queries ──────────────────────────────────────────────────────

export function useProfile() {
  return useQuery<UserProfile>({
    queryKey: chatKeys.profile(),
    queryFn: () => chatService.getProfile(),
    staleTime: STALE_TIMES.static,
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: Partial<UserProfile>) => chatService.updateProfile(data),
    onSuccess: (updated) => {
      queryClient.setQueryData(chatKeys.profile(), updated);
    },
    onError: (error) => {
      console.error("Failed to update profile:", error);
    },
  });
}

// ─── Categories Query ──────────────────────────────────────────────────────

export function useCategories() {
  return useQuery<string[]>({
    queryKey: chatKeys.categories(),
    queryFn: () => chatService.listCategories(),
    staleTime: STALE_TIMES.rare,
  });
}

// ─── Agent Health Query ────────────────────────────────────────────────────

export function useAgentHealth() {
  return useQuery<boolean>({
    queryKey: chatKeys.agentHealth(),
    queryFn: () => chatService.checkAgentHealth(),
    staleTime: STALE_TIMES.instant,
    refetchInterval: 30_000,
  });
}
