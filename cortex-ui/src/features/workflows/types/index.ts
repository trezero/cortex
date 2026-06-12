export type RunStatus = "pending" | "dispatched" | "running" | "paused" | "completed" | "failed" | "cancelled";
export type NodeState = "pending" | "running" | "waiting_approval" | "completed" | "failed" | "skipped" | "cancelled";

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  yaml_content: string;
  parsed_definition: Record<string, unknown>;
  version: number;
  is_latest: boolean;
  tags: string[];
  origin: string;
  created_at: string;
  deleted_at: string | null;
}

export interface WorkflowRun {
  id: string;
  definition_id: string;
  project_id: string | null;
  backend_id: string | null;
  status: RunStatus;
  triggered_by: string | null;
  trigger_context: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface WorkflowNode {
  id: string;
  workflow_run_id: string;
  node_id: string;
  state: NodeState;
  output: string | null;
  error: string | null;
  session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ExecutionBackend {
  id: string;
  name: string;
  base_url: string;
  project_id: string | null;
  status: "healthy" | "unhealthy" | "disconnected";
  last_heartbeat_at: string | null;
  registered_at: string;
}

export interface WorkflowRunDetail {
  run: WorkflowRun;
  nodes: WorkflowNode[];
}

export interface CreateRunRequest {
  definition_id: string;
  project_id?: string;
  backend_id?: string;
  trigger_context?: Record<string, unknown>;
}

export interface CreateDefinitionRequest {
  name: string;
  yaml_content: string;
  description?: string;
  project_id?: string;
  tags?: string[];
}

export interface WorkflowSSEEvent {
  type: "node_state_changed" | "run_status_changed" | "approval_requested" | "approval_resolved" | "node_progress";
  data: Record<string, unknown>;
}

export interface ApprovalRequest {
  id: string;
  workflow_run_id: string;
  workflow_node_id: string;
  yaml_node_id: string;
  approval_type: string;
  payload: { components?: A2UIComponent[]; raw_output?: string };
  status: "pending" | "approved" | "rejected" | "expired";
  channels_notified: string[];
  resolved_by: string | null;
  resolved_via: string | null;
  resolved_comment: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface A2UIComponent {
  type: string;
  id: string;
  props: Record<string, unknown>;
  zone?: string;
}

export interface ResolveApprovalRequest {
  decision: "approved" | "rejected";
  comment?: string;
}

export interface EditorNode {
  id: string;
  command: string;
  prompt: string;
  depends_on: string[];
  approval_required: boolean;
  when?: string;
}

export interface WorkflowCommand {
  id: string;
  name: string;
  prompt_template: string;
  description: string | null;
  is_builtin: boolean;
  created_at: string;
}

export interface CreateCommandRequest {
  name: string;
  prompt_template: string;
  description?: string;
}

export interface DiscoveredPattern {
  id: string;
  pattern_name: string;
  description: string | null;
  pattern_type: string;
  sequence_pattern: Record<string, unknown> | null;
  repos_involved: string[];
  frequency_score: number;
  cross_repo_score: number;
  automation_potential: number;
  final_score: number;
  suggested_yaml: string | null;
  status: "pending_review" | "accepted" | "dismissed" | "expired";
  discovered_at: string;
}
