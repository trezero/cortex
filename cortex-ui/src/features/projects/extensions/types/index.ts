export interface PluginManifest {
  hooks: string[];
  mcp_server: boolean;
  dependencies: string[];
  skills_included: string[];
  min_python_version: string;
}

export interface CommandMetadata {
  command_group: string | null;
  filename: string;
}

export type AgentCompatibilityState = "pending" | "stale" | "invalid" | "current";

export interface ExtensionTarget {
  id: string;
  extension_id: string;
  agent?: string;
  mode: "direct" | "adapted";
  scope: "repository" | "global";
  reviewed_source_hash: string;
  reviewed_extension_hash: string;
  payload_hash: string;
  reviewed_by: string;
  reviewed_at: string;
  compatibility_state: AgentCompatibilityState;
}

export interface Extension {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content?: string;
  content_hash: string;
  source_digest?: string;
  current_version: number;
  is_required: boolean;
  is_default: boolean;
  is_validated: boolean;
  tags: string[];
  type: "skill" | "plugin" | "command";
  plugin_manifest?: PluginManifest | CommandMetadata | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  targets?: ExtensionTarget[];
}

export interface System {
  id: string;
  fingerprint: string;
  name: string;
  hostname: string | null;
  os: string | null;
  agent: string;
  last_seen_at: string;
  created_at: string;
}

export interface SystemExtension {
  id: string;
  system_id: string;
  extension_id: string;
  project_id: string;
  status: "pending_install" | "installed" | "pending_remove" | "removed";
  installed_content_hash: string | null;
  installed_version: number | null;
  has_local_changes: boolean;
  updated_at: string;
  cortex_extensions?: Extension;
}

export interface SystemWithExtensions extends System {
  extensions: SystemExtension[];
}

export interface ProjectExtensionsResponse {
  all_extensions: Extension[];
  systems: SystemWithExtensions[];
}

export interface ProjectSystemsResponse {
  systems: System[];
  count: number;
}

export interface ExtensionsListResponse {
  extensions: Extension[];
  count: number;
}
