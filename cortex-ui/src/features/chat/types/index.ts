/**
 * Chat Feature Types
 *
 * Interfaces matching the database schema and agent service SSE protocol.
 */

// Core entity types

export interface ChatConversation {
  id: string;
  title: string | null;
  project_id: string | null;
  conversation_type: string;
  model_config: Record<string, unknown>;
  action_mode: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  metadata: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string | null;
  tool_calls: ToolCall[] | null;
  tool_results: ToolResult[] | null;
  model: string | null;
  tokens_used: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface UserProfile {
  id: string;
  display_name: string | null;
  bio: string | null;
  long_term_goals: string[] | null;
  current_priorities: string[] | null;
  preferences: Record<string, unknown> | null;
  onboarding_completed: boolean;
  created_at: string;
  updated_at: string;
}

// Tool call/result types

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  tool_call_id: string;
  name: string;
  result: unknown;
  error: string | null;
}

// SSE event types

export type SSEEventType =
  | "text_delta"
  | "tool_start"
  | "tool_result"
  | "message_complete"
  | "action_request"
  | "error";

export interface SSEEvent {
  type: SSEEventType;
}

export interface TextDeltaEvent extends SSEEvent {
  type: "text_delta";
  delta: string;
}

export interface ToolStartEvent extends SSEEvent {
  type: "tool_start";
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResultEvent extends SSEEvent {
  type: "tool_result";
  tool_call_id: string;
  tool_name: string;
  result: unknown;
  error: string | null;
}

export interface MessageCompleteEvent extends SSEEvent {
  type: "message_complete";
  message_id: string;
  conversation_id: string;
  content: string;
  tokens_used: number | null;
}

export interface ActionRequestEvent extends SSEEvent {
  type: "action_request";
  action_id: string;
  action_type: string;
  description: string;
  payload: Record<string, unknown>;
}

export interface ErrorEvent extends SSEEvent {
  type: "error";
  error: string;
  details: string | null;
}

export type AnySSEEvent =
  | TextDeltaEvent
  | ToolStartEvent
  | ToolResultEvent
  | MessageCompleteEvent
  | ActionRequestEvent
  | ErrorEvent;

// In-progress stream state

export interface StreamingMessage {
  conversation_id: string;
  content: string;
  tool_calls_in_progress: ToolStartEvent[];
  is_complete: boolean;
  error: string | null;
}

// Request types

export interface CreateConversationRequest {
  title?: string;
  project_id?: string | null;
  model_config?: Record<string, unknown>;
}

export interface UpdateConversationRequest {
  title?: string;
  model_config?: Record<string, unknown>;
  action_mode?: boolean;
}

export interface SendMessageRequest {
  conversation_id: string;
  content: string;
  model?: string | null;
  metadata?: Record<string, unknown> | null;
  conversation_history?: Array<{ role: string; content: string }>;
}
