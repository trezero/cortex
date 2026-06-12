import { useState } from "react";

import { useWorkflowDefinitions, useWorkflowRuns } from "../hooks/useWorkflowQueries";
import type { DiscoveredPattern, WorkflowDefinition, WorkflowRun } from "../types";
import { ApprovalDetail } from "./ApprovalDetail";
import { ApprovalList } from "./ApprovalList";
import { CommandEditor } from "./CommandEditor";
import { SuggestedWorkflows } from "./SuggestedWorkflows";
import { WorkflowEditor } from "./WorkflowEditor";
import { WorkflowRunCard } from "./WorkflowRunCard";
import { WorkflowRunView } from "./WorkflowRunView";

type Tab = "runs" | "definitions" | "approvals" | "commands" | "suggestions";

const TABS: { id: Tab; label: string }[] = [
  { id: "runs", label: "Runs" },
  { id: "definitions", label: "Definitions" },
  { id: "approvals", label: "Approvals" },
  { id: "commands", label: "Commands" },
  { id: "suggestions", label: "Suggestions" },
];

export default function WorkflowsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("runs");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [editingDefinition, setEditingDefinition] = useState<WorkflowDefinition | null | undefined>(undefined);
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(null);

  return (
    <div className="flex flex-col h-full p-6 gap-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-100">Workflows</h1>
        <p className="text-sm text-gray-400 mt-1">Manage and monitor automated workflow runs</p>
      </div>

      {/* Tab Bar */}
      <div className="flex items-center gap-1 border-b border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-cyan-500 text-cyan-400"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        {activeTab === "runs" && (
          <RunsTab
            selectedRunId={selectedRunId}
            onSelectRun={setSelectedRunId}
            onClearRun={() => setSelectedRunId(null)}
            onApprovalClick={(id) => {
              setSelectedApprovalId(id);
              setActiveTab("approvals");
            }}
          />
        )}

        {activeTab === "definitions" && (
          <DefinitionsTab
            editingDefinition={editingDefinition}
            onEdit={setEditingDefinition}
            onCancelEdit={() => setEditingDefinition(undefined)}
            onSaved={() => setEditingDefinition(undefined)}
          />
        )}

        {activeTab === "approvals" && (
          <ApprovalsTab
            selectedApprovalId={selectedApprovalId}
            onSelectApproval={setSelectedApprovalId}
          />
        )}

        {activeTab === "commands" && <CommandEditor />}

        {activeTab === "suggestions" && (
          <SuggestedWorkflows
            onCustomize={(pattern: DiscoveredPattern) => {
              // Pre-populate the definition editor from the pattern's suggested YAML
              const partialDef: WorkflowDefinition = {
                id: pattern.id,
                name: pattern.pattern_name,
                description: pattern.description,
                project_id: null,
                yaml_content: pattern.suggested_yaml ?? "",
                parsed_definition: {},
                version: 1,
                is_latest: true,
                tags: [],
                origin: "suggestion",
                created_at: pattern.discovered_at,
                deleted_at: null,
              };
              setEditingDefinition(partialDef);
              setActiveTab("definitions");
            }}
          />
        )}
      </div>
    </div>
  );
}

// -- Runs Tab ------------------------------------------------------------------

interface RunsTabProps {
  selectedRunId: string | null;
  onSelectRun: (id: string) => void;
  onClearRun: () => void;
  onApprovalClick: (id: string) => void;
}

function RunsTab({ selectedRunId, onSelectRun, onClearRun, onApprovalClick }: RunsTabProps) {
  const { data: runs, isLoading, error } = useWorkflowRuns();

  if (selectedRunId) {
    return (
      <WorkflowRunView
        runId={selectedRunId}
        onBack={onClearRun}
        onApprovalClick={onApprovalClick}
      />
    );
  }

  if (isLoading) {
    return <div className="text-gray-400 text-sm">Loading runs...</div>;
  }

  if (error) {
    return (
      <div className="text-red-400 text-sm">
        Failed to load runs: {error instanceof Error ? error.message : "Unknown error"}
      </div>
    );
  }

  if (!runs?.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <p className="text-gray-500 text-sm">No workflow runs found</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {(runs as WorkflowRun[]).map((run) => (
        <WorkflowRunCard key={run.id} run={run} onClick={onSelectRun} />
      ))}
    </div>
  );
}

// -- Definitions Tab ----------------------------------------------------------

interface DefinitionsTabProps {
  editingDefinition: WorkflowDefinition | null | undefined;
  onEdit: (def: WorkflowDefinition | null) => void;
  onCancelEdit: () => void;
  onSaved: () => void;
}

function DefinitionsTab({ editingDefinition, onEdit, onCancelEdit, onSaved }: DefinitionsTabProps) {
  const { data: definitions, isLoading, error } = useWorkflowDefinitions();

  // editingDefinition === null means "create new"
  // editingDefinition === undefined means "list view"
  if (editingDefinition !== undefined) {
    return (
      <WorkflowEditor
        initialDefinition={editingDefinition ?? undefined}
        onSave={onSaved}
        onCancel={onCancelEdit}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => onEdit(null)}
          className="text-sm px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
        >
          New Workflow
        </button>
      </div>

      {isLoading && <div className="text-gray-400 text-sm">Loading definitions...</div>}

      {error && (
        <div className="text-red-400 text-sm">
          Failed to load definitions: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {!isLoading && !error && !definitions?.length && (
        <div className="flex flex-col items-center justify-center py-16">
          <p className="text-gray-500 text-sm">No workflow definitions yet</p>
        </div>
      )}

      <div className="space-y-2">
        {definitions?.map((def) => (
          <button
            key={def.id}
            type="button"
            onClick={() => onEdit(def)}
            className="w-full text-left bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4
              hover:border-cyan-500/30 transition-colors"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-gray-200">{def.name}</span>
              <span className="text-xs text-gray-500">v{def.version}</span>
            </div>
            {def.description && (
              <p className="text-xs text-gray-400 truncate">{def.description}</p>
            )}
            {def.tags && def.tags.length > 0 && (
              <div className="flex gap-1 mt-2 flex-wrap">
                {def.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// -- Approvals Tab ------------------------------------------------------------

interface ApprovalsTabProps {
  selectedApprovalId: string | null;
  onSelectApproval: (id: string) => void;
}

function ApprovalsTab({ selectedApprovalId, onSelectApproval }: ApprovalsTabProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ApprovalList onSelect={onSelectApproval} selectedId={selectedApprovalId ?? undefined} />
      {selectedApprovalId && (
        <ApprovalDetail approvalId={selectedApprovalId} />
      )}
    </div>
  );
}
