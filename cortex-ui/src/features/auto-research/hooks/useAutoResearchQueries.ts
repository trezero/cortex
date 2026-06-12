import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "../../shared/config/queryPatterns";
import { useSmartPolling } from "../../shared/hooks";
import { autoResearchService } from "../services/autoResearchService";
import type { StartOptimizationRequest } from "../types";

export const autoResearchKeys = {
  all: ["auto-research"] as const,
  suites: () => [...autoResearchKeys.all, "suites"] as const,
  jobs: () => [...autoResearchKeys.all, "jobs"] as const,
  jobDetail: (id: string) => [...autoResearchKeys.all, "job", id] as const,
};

export function useEvalSuites() {
  return useQuery({
    queryKey: autoResearchKeys.suites(),
    queryFn: () => autoResearchService.listSuites(),
    staleTime: STALE_TIMES.rare,
  });
}

export function useAutoResearchJobs() {
  return useQuery({
    queryKey: autoResearchKeys.jobs(),
    queryFn: () => autoResearchService.listJobs(),
    staleTime: STALE_TIMES.normal,
  });
}

export function useAutoResearchJob(jobId: string | null) {
  const { refetchInterval } = useSmartPolling(3000);

  return useQuery({
    queryKey: jobId ? autoResearchKeys.jobDetail(jobId) : DISABLED_QUERY_KEY,
    queryFn: () => (jobId ? autoResearchService.getJob(jobId) : Promise.reject("No job ID")),
    enabled: !!jobId,
    staleTime: STALE_TIMES.frequent,
    refetchInterval: (query) => {
      // Stop polling when job reaches terminal state
      const status = query.state.data?.job?.status;
      if (status && ["completed", "failed", "cancelled"].includes(status)) return false;
      return refetchInterval;
    },
  });
}

export function useStartOptimization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: StartOptimizationRequest) => autoResearchService.startOptimization(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: autoResearchKeys.jobs() });
    },
  });
}

export function useApplyResult() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => autoResearchService.applyResult(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: autoResearchKeys.jobs() });
    },
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => autoResearchService.cancelJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: autoResearchKeys.jobDetail(jobId) });
      queryClient.invalidateQueries({ queryKey: autoResearchKeys.jobs() });
    },
  });
}
