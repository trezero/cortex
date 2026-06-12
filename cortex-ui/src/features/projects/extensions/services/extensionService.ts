import { callAPIWithETag } from "@/features/shared/api/apiClient";
import type { ExtensionsListResponse, ProjectExtensionsResponse, ProjectSystemsResponse } from "../types";

export const extensionService = {
  async getProjectExtensions(projectId: string): Promise<ProjectExtensionsResponse> {
    return callAPIWithETag<ProjectExtensionsResponse>(`/api/projects/${projectId}/extensions`);
  },

  async getProjectSystems(projectId: string): Promise<ProjectSystemsResponse> {
    return callAPIWithETag<ProjectSystemsResponse>(`/api/projects/${projectId}/systems`);
  },

  async getAllExtensions(): Promise<ExtensionsListResponse> {
    return callAPIWithETag<ExtensionsListResponse>("/api/extensions");
  },

  async installExtension(projectId: string, extensionId: string, systemIds: string[]): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/extensions/${extensionId}/install`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_ids: systemIds }),
    });
    if (!response.ok) throw new Error(`Failed to install extension: ${response.statusText}`);
  },

  async removeExtension(projectId: string, extensionId: string, systemIds: string[]): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/extensions/${extensionId}/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_ids: systemIds }),
    });
    if (!response.ok) throw new Error(`Failed to remove extension: ${response.statusText}`);
  },

  async unlinkSystem(projectId: string, systemId: string): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/systems/${systemId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to unlink system: ${response.statusText}`);
  },

  async linkExtension(projectId: string, extensionId: string): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/extensions/${extensionId}/link`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(`Failed to link extension: ${response.statusText}`);
  },

  async unlinkExtension(projectId: string, extensionId: string): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/extensions/${extensionId}/link`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to unlink extension: ${response.statusText}`);
  },

  async setExtensionDefault(extensionId: string, isDefault: boolean): Promise<void> {
    const response = await fetch(`/api/extensions/${extensionId}/default`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_default: isDefault }),
    });
    if (!response.ok) throw new Error(`Failed to update extension default: ${response.statusText}`);
  },
};
