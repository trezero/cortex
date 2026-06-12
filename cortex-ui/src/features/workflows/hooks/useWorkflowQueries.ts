import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { useSmartPolling } from "@/features/shared/hooks";

import { workflowService } from "../services/workflowService";
import type { CreateCommandRequest, CreateDefinitionRequest, CreateRunRequest, ResolveApprovalRequest } from "../types";

export const workflowKeys = {
  all: ["workflows"] as const,
  definitions: () => [...workflowKeys.all, "definitions"] as const,
  definitionDetail: (id: string) => [...workflowKeys.all, "definitions", id] as const,
  runs: () => [...workflowKeys.all, "runs"] as const,
  runDetail: (id: string) => [...workflowKeys.all, "runs", id] as const,
  backends: () => [...workflowKeys.all, "backends"] as const,
  approvals: () => [...workflowKeys.all, "approvals"] as const,
  approvalDetail: (id: string) => [...workflowKeys.all, "approvals", id] as const,
  commands: () => [...workflowKeys.all, "commands"] as const,
  suggestions: () => [...workflowKeys.all, "suggestions"] as const,
};

export function useWorkflowDefinitions(projectId?: string) {
  return useQuery({
    queryKey: workflowKeys.definitions(),
    queryFn: () => workflowService.listDefinitions(projectId),
    staleTime: STALE_TIMES.normal,
  });
}

export function useWorkflowDefinition(id: string | undefined) {
  return useQuery({
    queryKey: id ? workflowKeys.definitionDetail(id) : DISABLED_QUERY_KEY,
    queryFn: () => (id ? workflowService.getDefinition(id) : Promise.reject("No ID")),
    enabled: !!id,
    staleTime: STALE_TIMES.normal,
  });
}

export function useCreateDefinition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDefinitionRequest) => workflowService.createDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.definitions() });
    },
  });
}

export function useWorkflowRuns(status?: string, projectId?: string) {
  const { refetchInterval } = useSmartPolling(5000);
  return useQuery({
    queryKey: workflowKeys.runs(),
    queryFn: () => workflowService.listRuns(status, projectId),
    refetchInterval,
    staleTime: STALE_TIMES.frequent,
  });
}

export function useWorkflowRun(runId: string | undefined) {
  const { refetchInterval } = useSmartPolling(3000);
  return useQuery({
    queryKey: runId ? workflowKeys.runDetail(runId) : DISABLED_QUERY_KEY,
    queryFn: () => (runId ? workflowService.getRun(runId) : Promise.reject("No ID")),
    enabled: !!runId,
    refetchInterval,
    staleTime: STALE_TIMES.realtime,
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRunRequest) => workflowService.createRun(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useCancelRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => workflowService.cancelRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useExecutionBackends() {
  return useQuery({
    queryKey: workflowKeys.backends(),
    queryFn: () => workflowService.listBackends(),
    staleTime: STALE_TIMES.normal,
  });
}

export function useApprovals(status?: string) {
  const { refetchInterval } = useSmartPolling(5000);
  return useQuery({
    queryKey: workflowKeys.approvals(),
    queryFn: () => workflowService.listApprovals(status),
    refetchInterval,
    staleTime: STALE_TIMES.frequent,
  });
}

export function useApprovalDetail(id: string | undefined) {
  return useQuery({
    queryKey: id ? workflowKeys.approvalDetail(id) : DISABLED_QUERY_KEY,
    queryFn: () => (id ? workflowService.getApproval(id) : Promise.reject("No ID")),
    enabled: !!id,
    staleTime: STALE_TIMES.frequent,
  });
}

export function useResolveApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ResolveApprovalRequest }) =>
      workflowService.resolveApproval(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.approvals() });
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useCommands() {
  return useQuery({
    queryKey: workflowKeys.commands(),
    queryFn: () => workflowService.listCommands(),
    staleTime: STALE_TIMES.normal,
  });
}

export function useCreateCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateCommandRequest) => workflowService.createCommand(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.commands() });
    },
  });
}

export function useUpdateCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreateCommandRequest> }) =>
      workflowService.updateCommand(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.commands() });
    },
  });
}

export function useDeleteCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => workflowService.deleteCommand(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.commands() });
    },
  });
}

export function useSuggestions(status?: string) {
  return useQuery({
    queryKey: workflowKeys.suggestions(),
    queryFn: () => workflowService.listSuggestions(status),
    staleTime: STALE_TIMES.normal,
  });
}

export function useAcceptSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, yaml }: { id: string; yaml?: string }) =>
      workflowService.acceptSuggestion(id, yaml),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workflowKeys.suggestions() });
      qc.invalidateQueries({ queryKey: workflowKeys.definitions() });
    },
  });
}

export function useDismissSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      workflowService.dismissSuggestion(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workflowKeys.suggestions() });
    },
  });
}
