import { callAPIWithETag } from "../../shared/api/apiClient";
import type {
  AutoResearchJob,
  AutoResearchJobWithIterations,
  EvalSuiteSummary,
  StartOptimizationRequest,
  StartOptimizationResponse,
} from "../types";

export const autoResearchService = {
  async listSuites(): Promise<{ success: boolean; suites: EvalSuiteSummary[] }> {
    return callAPIWithETag("/api/auto-research/suites");
  },

  async startOptimization(request: StartOptimizationRequest): Promise<StartOptimizationResponse> {
    return callAPIWithETag("/api/auto-research/start", {
      method: "POST",
      body: JSON.stringify(request),
    });
  },

  async listJobs(): Promise<{ success: boolean; jobs: AutoResearchJob[] }> {
    return callAPIWithETag("/api/auto-research/jobs");
  },

  async getJob(jobId: string): Promise<{ success: boolean; job: AutoResearchJobWithIterations }> {
    return callAPIWithETag(`/api/auto-research/jobs/${jobId}`);
  },

  async applyResult(jobId: string): Promise<{ success: boolean; file_path: string }> {
    return callAPIWithETag(`/api/auto-research/jobs/${jobId}/apply`, { method: "POST" });
  },

  async cancelJob(jobId: string): Promise<{ success: boolean }> {
    return callAPIWithETag(`/api/auto-research/jobs/${jobId}/cancel`, { method: "POST" });
  },
};
