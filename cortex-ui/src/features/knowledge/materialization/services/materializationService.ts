import { callAPIWithETag } from "../../../shared/api/apiClient";
import type { MaterializationHistoryResponse, MaterializationRecord } from "../types";

export const materializationService = {
  async getHistory(projectId?: string, status?: string): Promise<MaterializationHistoryResponse> {
    const params = new URLSearchParams();
    if (projectId) params.append("project_id", projectId);
    if (status) params.append("status", status);
    const query = params.toString();
    return callAPIWithETag<MaterializationHistoryResponse>(`/api/materialization/history${query ? `?${query}` : ""}`);
  },

  async getRecord(id: string): Promise<MaterializationRecord> {
    return callAPIWithETag<MaterializationRecord>(`/api/materialization/${id}`);
  },

  async updateStatus(id: string, status: string): Promise<{ success: boolean }> {
    return callAPIWithETag<{ success: boolean }>(`/api/materialization/${id}/status?status=${status}`, {
      method: "PUT",
    });
  },

  async deleteRecord(id: string): Promise<{ success: boolean }> {
    return callAPIWithETag<{ success: boolean }>(`/api/materialization/${id}`, {
      method: "DELETE",
    });
  },
};
