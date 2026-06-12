/**
 * Repository Service
 *
 * Service layer for repository CRUD operations.
 * All methods use callAPIWithETag for automatic ETag caching.
 */

import { callAPIWithETag } from "@/features/shared/api/apiClient";
import type { ConfiguredRepository, CreateRepositoryRequest, UpdateRepositoryRequest } from "../types/repository";

interface ProjectRepositoryFallback {
  id: string;
  github_repo?: string;
}

const DEFAULT_WORKFLOW_COMMANDS: ConfiguredRepository["default_commands"] = ["create-branch", "planning", "execute"];

function normalizeGithubUrl(url: string): string {
  return url.trim().replace(/\.git$/i, "").replace(/\/+$/, "");
}

function extractOwnerAndRepo(url: string): { owner: string | null; repoName: string } {
  const match = url.match(/^https?:\/\/github\.com\/([^/]+)\/([^/]+)$/i);
  if (!match) {
    const fallback = url.split("/").filter(Boolean).pop() || url;
    return { owner: null, repoName: fallback };
  }
  return { owner: match[1], repoName: match[2] };
}

function mapProjectsToRepositories(projects: ProjectRepositoryFallback[]): ConfiguredRepository[] {
  const now = new Date().toISOString();
  const seen = new Set<string>();
  const repositories: ConfiguredRepository[] = [];

  for (const project of projects) {
    if (!project.github_repo) continue;

    const normalizedUrl = normalizeGithubUrl(project.github_repo);
    if (!/^https?:\/\/github\.com\/[^/]+\/[^/]+$/i.test(normalizedUrl)) continue;

    const dedupeKey = normalizedUrl.toLowerCase();
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    const { owner, repoName } = extractOwnerAndRepo(normalizedUrl);

    repositories.push({
      id: `project-${project.id}`,
      repository_url: normalizedUrl,
      display_name: repoName,
      owner,
      default_branch: null,
      is_verified: false,
      last_verified_at: null,
      default_sandbox_type: "git_worktree",
      default_commands: DEFAULT_WORKFLOW_COMMANDS,
      created_at: now,
      updated_at: now,
    });
  }

  return repositories;
}

/**
 * List all configured repositories
 * @returns Project repositories mapped into ConfiguredRepository shape
 */
export async function listRepositories(): Promise<ConfiguredRepository[]> {
  const response = await callAPIWithETag<{ projects: ProjectRepositoryFallback[] }>("/api/projects", {
    method: "GET",
  });
  return mapProjectsToRepositories(response.projects || []);
}

/**
 * Create a new configured repository
 * @param request - Repository creation request with URL and optional verification
 * @returns The created repository with metadata
 */
export async function createRepository(request: CreateRepositoryRequest): Promise<ConfiguredRepository> {
  return callAPIWithETag<ConfiguredRepository>("/api/agent-work-orders/repositories", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
}

/**
 * Update an existing configured repository
 * @param id - Repository ID
 * @param request - Partial update request with fields to modify
 * @returns The updated repository
 */
export async function updateRepository(id: string, request: UpdateRepositoryRequest): Promise<ConfiguredRepository> {
  return callAPIWithETag<ConfiguredRepository>(`/api/agent-work-orders/repositories/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
}

/**
 * Delete a configured repository
 * @param id - Repository ID to delete
 */
export async function deleteRepository(id: string): Promise<void> {
  await callAPIWithETag<void>(`/api/agent-work-orders/repositories/${id}`, {
    method: "DELETE",
  });
}

/**
 * Verify repository access and update metadata
 * Re-verifies GitHub repository access and updates display_name, owner, default_branch
 * @param id - Repository ID to verify
 * @returns Verification result with is_accessible boolean
 */
export async function verifyRepositoryAccess(id: string): Promise<{ is_accessible: boolean; repository_id: string }> {
  return callAPIWithETag<{ is_accessible: boolean; repository_id: string }>(
    `/api/agent-work-orders/repositories/${id}/verify`,
    {
      method: "POST",
    },
  );
}

// Export all methods as named exports and default object
export const repositoryService = {
  listRepositories,
  createRepository,
  updateRepository,
  deleteRepository,
  verifyRepositoryAccess,
};

export default repositoryService;
