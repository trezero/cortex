/**
 * Project Knowledge Query Hooks
 * Handles fetching knowledge sources scoped to a project
 */
import { useQuery } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { projectKnowledgeService } from "../services/projectKnowledgeService";
import type { KnowledgeItemsResponse } from "../types";

export const projectKnowledgeKeys = {
	all: ["projects", "knowledge-sources"] as const,
	byProject: (projectId: string) => ["projects", projectId, "knowledge-sources"] as const,
};

export function useProjectKnowledgeSources(projectId: string | undefined) {
	return useQuery<KnowledgeItemsResponse>({
		queryKey: projectId ? projectKnowledgeKeys.byProject(projectId) : DISABLED_QUERY_KEY,
		queryFn: () =>
			projectId
				? projectKnowledgeService.getProjectKnowledgeSources(projectId, { per_page: 100 })
				: Promise.reject("No project ID"),
		enabled: !!projectId,
		staleTime: STALE_TIMES.normal,
	});
}
