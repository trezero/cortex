export interface MaterializationRecord {
  id: string;
  project_id: string;
  project_path: string;
  topic: string;
  filename: string;
  file_path: string;
  source_ids: string[];
  original_urls: string[];
  synthesis_model: string | null;
  word_count: number;
  status: "pending" | "active" | "stale" | "archived";
  access_count: number;
  last_accessed_at: string | null;
  materialized_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface MaterializationHistoryResponse {
  items: MaterializationRecord[];
  total: number;
}

export interface MaterializationExecuteResponse {
  success: boolean;
  progress_id: string;
  materialization_id: string | null;
  file_path: string | null;
  filename: string | null;
  word_count: number;
  summary: string | null;
  reason: string | null;
}
