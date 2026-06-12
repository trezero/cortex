/**
 * Project Knowledge Service
 * Fetches knowledge sources scoped to a specific project
 */
import { callAPIWithETag } from "@/features/shared/api/apiClient";
import type { KnowledgeItemsResponse } from "../types";

export const projectKnowledgeService = {
	async getProjectKnowledgeSources(
		projectId: string,
		params?: { page?: number; per_page?: number; search?: string; knowledge_type?: string },
	): Promise<KnowledgeItemsResponse> {
		const searchParams = new URLSearchParams();
		if (params?.page) searchParams.append("page", params.page.toString());
		if (params?.per_page) searchParams.append("per_page", params.per_page.toString());
		if (params?.search) searchParams.append("search", params.search);
		if (params?.knowledge_type) searchParams.append("knowledge_type", params.knowledge_type);

		const queryString = searchParams.toString();
		const endpoint = `/api/projects/${projectId}/knowledge-sources${queryString ? `?${queryString}` : ""}`;

		return callAPIWithETag<KnowledgeItemsResponse>(endpoint);
	},
};
