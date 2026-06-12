import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/features/shared/hooks/useToast";
import { STALE_TIMES } from "../../../shared/config/queryPatterns";
import { materializationService } from "../services/materializationService";
import type { MaterializationHistoryResponse } from "../types";

export const materializationKeys = {
  all: ["materialization"] as const,
  lists: () => [...materializationKeys.all, "list"] as const,
  history: (projectId?: string, status?: string) => [...materializationKeys.all, "history", projectId, status] as const,
  detail: (id: string) => [...materializationKeys.all, "detail", id] as const,
};

export function useMaterializationHistory(projectId?: string, status?: string) {
  return useQuery<MaterializationHistoryResponse>({
    queryKey: materializationKeys.history(projectId, status),
    queryFn: () => materializationService.getHistory(projectId, status),
    staleTime: STALE_TIMES.normal,
  });
}

export function useDeleteMaterialization() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: (id: string) => materializationService.deleteRecord(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: materializationKeys.lists() });
      showToast("Materialization deleted", "success");
    },
    onError: () => {
      showToast("Failed to delete materialization", "error");
    },
  });
}

export function useUpdateMaterializationStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => materializationService.updateStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: materializationKeys.lists() });
    },
  });
}
