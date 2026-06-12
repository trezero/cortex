export interface EvalSuiteSummary {
  id: string;
  name: string;
  description: string;
  target_file: string;
  test_case_count: number;
}

export interface EvalSignalResult {
  value: boolean;
  weight: number;
  critical: boolean;
  reasoning: string | null;
}

export interface AutoResearchIteration {
  id: string;
  job_id: string;
  iteration_number: number;
  payload: string;
  scalar_score: number;
  signals: Record<string, EvalSignalResult>;
  is_frontier: boolean;
  created_at: string;
}

export interface AutoResearchJob {
  id: string;
  eval_suite_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  target_file: string;
  baseline_payload: string;
  baseline_score: number | null;
  best_payload: string | null;
  best_score: number | null;
  max_iterations: number;
  completed_iterations: number;
  model: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AutoResearchJobWithIterations extends AutoResearchJob {
  iterations: AutoResearchIteration[];
}

export interface StartOptimizationRequest {
  eval_suite_id: string;
  max_iterations: number;
  model?: string | null;
}

export interface StartOptimizationResponse {
  success: boolean;
  job_id: string;
  progress_id: string;
}
