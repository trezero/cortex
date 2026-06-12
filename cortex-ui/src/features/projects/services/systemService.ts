import { callAPIWithETag } from "@/features/shared/api/apiClient";

export interface SystemSummary {
  id: string;
  name: string;
  os: string | null;
}

interface SystemsResponse {
  systems: SystemSummary[];
  count: number;
}

export const systemService = {
  async listSystems(): Promise<SystemSummary[]> {
    const response = await callAPIWithETag<SystemsResponse>("/api/systems");
    return response.systems;
  },
};
