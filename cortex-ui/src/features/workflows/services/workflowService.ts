import { callAPIWithETag } from "../../shared/api/apiClient";
import type {
  ApprovalRequest,
  CreateCommandRequest,
  CreateDefinitionRequest,
  CreateRunRequest,
  DiscoveredPattern,
  ExecutionBackend,
  ResolveApprovalRequest,
  WorkflowCommand,
  WorkflowDefinition,
  WorkflowRun,
  WorkflowRunDetail,
} from "../types";

export const workflowService = {
  async listDefinitions(projectId?: string): Promise<WorkflowDefinition[]> {
    const params = projectId ? `?project_id=${projectId}` : "";
    return callAPIWithETag<WorkflowDefinition[]>(`/api/workflows/definitions${params}`);
  },

  async getDefinition(id: string): Promise<WorkflowDefinition> {
    return callAPIWithETag<WorkflowDefinition>(`/api/workflows/definitions/${id}`);
  },

  async createDefinition(data: CreateDefinitionRequest): Promise<WorkflowDefinition> {
    return callAPIWithETag<WorkflowDefinition>("/api/workflows/definitions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async deleteDefinition(id: string): Promise<void> {
    await callAPIWithETag(`/api/workflows/definitions/${id}`, { method: "DELETE" });
  },

  async listRuns(status?: string, projectId?: string): Promise<WorkflowRun[]> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (projectId) params.set("project_id", projectId);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return callAPIWithETag<WorkflowRun[]>(`/api/workflows${qs}`);
  },

  async getRun(runId: string): Promise<WorkflowRunDetail> {
    return callAPIWithETag<WorkflowRunDetail>(`/api/workflows/${runId}`);
  },

  async createRun(data: CreateRunRequest): Promise<{ run_id: string; status: string }> {
    return callAPIWithETag<{ run_id: string; status: string }>("/api/workflows", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async cancelRun(runId: string): Promise<void> {
    await callAPIWithETag(`/api/workflows/${runId}/cancel`, { method: "POST" });
  },

  async listBackends(): Promise<ExecutionBackend[]> {
    return callAPIWithETag<ExecutionBackend[]>("/api/workflows/backends");
  },

  async listApprovals(status?: string): Promise<ApprovalRequest[]> {
    const params = status ? `?status=${status}` : "";
    return callAPIWithETag<ApprovalRequest[]>(`/api/workflows/approvals${params}`);
  },

  async getApproval(id: string): Promise<ApprovalRequest> {
    return callAPIWithETag<ApprovalRequest>(`/api/workflows/approvals/${id}`);
  },

  async resolveApproval(id: string, data: ResolveApprovalRequest): Promise<{ resolved: boolean }> {
    return callAPIWithETag<{ resolved: boolean }>(`/api/workflows/approvals/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async listCommands(): Promise<WorkflowCommand[]> {
    return callAPIWithETag<WorkflowCommand[]>("/api/workflows/commands");
  },

  async createCommand(data: CreateCommandRequest): Promise<WorkflowCommand> {
    return callAPIWithETag<WorkflowCommand>("/api/workflows/commands", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateCommand(id: string, data: Partial<CreateCommandRequest>): Promise<WorkflowCommand> {
    return callAPIWithETag<WorkflowCommand>(`/api/workflows/commands/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async deleteCommand(id: string): Promise<void> {
    await callAPIWithETag(`/api/workflows/commands/${id}`, { method: "DELETE" });
  },

  async listSuggestions(status?: string): Promise<DiscoveredPattern[]> {
    const params = status ? `?status=${status}` : "";
    return callAPIWithETag<DiscoveredPattern[]>(`/api/patterns/suggestions${params}`);
  },

  async acceptSuggestion(id: string, customizedYaml?: string): Promise<{ accepted: boolean }> {
    return callAPIWithETag<{ accepted: boolean }>(`/api/patterns/suggestions/${id}/accept`, {
      method: "POST",
      body: JSON.stringify({ customized_yaml: customizedYaml }),
    });
  },

  async dismissSuggestion(id: string, reason?: string): Promise<{ dismissed: boolean }> {
    return callAPIWithETag<{ dismissed: boolean }>(`/api/patterns/suggestions/${id}/dismiss`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },
};
