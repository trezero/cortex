import * as yaml from "js-yaml";
import { useCallback, useMemo, useState } from "react";

import { useCreateDefinition } from "../hooks/useWorkflowQueries";
import type { EditorNode, WorkflowDefinition } from "../types";
import { YamlPanel } from "./YamlPanel";
import { NodeForm } from "./NodeForm";
import { MetadataForm } from "./editor/MetadataForm";
import { NodeList } from "./editor/NodeList";

interface WorkflowEditorProps {
  initialDefinition?: WorkflowDefinition;
  onSave?: (definitionId: string) => void;
  onCancel?: () => void;
}

interface WorkflowState {
  name: string;
  description: string;
  tags: string[];
  nodes: EditorNode[];
}

function createDefaultNode(): EditorNode {
  return {
    id: `step-${Date.now().toString(36)}`,
    command: "",
    prompt: "",
    depends_on: [],
    approval_required: false,
  };
}

function parseInitialState(definition?: WorkflowDefinition): WorkflowState {
  if (!definition) {
    return { name: "", description: "", tags: [], nodes: [] };
  }

  let nodes: EditorNode[] = [];
  try {
    const parsed = yaml.load(definition.yaml_content) as Record<string, unknown> | null;
    if (parsed && typeof parsed === "object" && "nodes" in parsed && Array.isArray(parsed.nodes)) {
      nodes = (parsed.nodes as Record<string, unknown>[]).map((n) => ({
        id: String(n.id ?? ""),
        command: String(n.command ?? ""),
        prompt: String(n.prompt ?? ""),
        depends_on: Array.isArray(n.depends_on) ? (n.depends_on as string[]) : [],
        approval_required: Boolean(n.approval_required),
        when: n.when ? String(n.when) : undefined,
      }));
    }
  } catch {
    // If YAML parsing fails, start with empty nodes
  }

  return {
    name: definition.name,
    description: definition.description ?? "",
    tags: definition.tags ?? [],
    nodes,
  };
}

function stateToYaml(state: WorkflowState): string {
  const doc: Record<string, unknown> = {
    name: state.name || undefined,
    description: state.description || undefined,
    tags: state.tags.length > 0 ? state.tags : undefined,
    nodes: state.nodes.map((n) => {
      const node: Record<string, unknown> = {
        id: n.id,
        command: n.command,
        prompt: n.prompt,
      };
      if (n.depends_on.length > 0) node.depends_on = n.depends_on;
      if (n.approval_required) node.approval_required = true;
      if (n.when) node.when = n.when;
      return node;
    }),
  };

  return yaml.dump(doc, { lineWidth: 120, noRefs: true, sortKeys: false });
}

function yamlToState(raw: string): WorkflowState {
  const parsed = yaml.load(raw) as Record<string, unknown> | null;
  if (!parsed || typeof parsed !== "object") {
    throw new Error("YAML must be a mapping (object)");
  }

  const nodes: EditorNode[] = [];
  if ("nodes" in parsed && Array.isArray(parsed.nodes)) {
    for (const n of parsed.nodes as Record<string, unknown>[]) {
      nodes.push({
        id: String(n.id ?? ""),
        command: String(n.command ?? ""),
        prompt: String(n.prompt ?? ""),
        depends_on: Array.isArray(n.depends_on) ? (n.depends_on as string[]) : [],
        approval_required: Boolean(n.approval_required),
        when: n.when ? String(n.when) : undefined,
      });
    }
  }

  return {
    name: typeof parsed.name === "string" ? parsed.name : "",
    description: typeof parsed.description === "string" ? parsed.description : "",
    tags: Array.isArray(parsed.tags) ? (parsed.tags as string[]).map(String) : [],
    nodes,
  };
}

export function WorkflowEditor({ initialDefinition, onSave, onCancel }: WorkflowEditorProps) {
  const [state, setState] = useState<WorkflowState>(() => parseInitialState(initialDefinition));
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const createDefinition = useCreateDefinition();

  const yamlContent = useMemo(() => stateToYaml(state), [state]);

  const allNodeIds = useMemo(() => state.nodes.map((n) => n.id), [state.nodes]);

  const selectedNode = useMemo(
    () => state.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [state.nodes, selectedNodeId],
  );

  const handleMetadataChange = useCallback((field: string, value: string | string[]) => {
    setState((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleAddNode = useCallback(() => {
    const newNode = createDefaultNode();
    setState((prev) => ({ ...prev, nodes: [...prev.nodes, newNode] }));
    setSelectedNodeId(newNode.id);
  }, []);

  const handleRemoveNode = useCallback(
    (id: string) => {
      setState((prev) => ({
        ...prev,
        nodes: prev.nodes
          .filter((n) => n.id !== id)
          .map((n) => ({ ...n, depends_on: n.depends_on.filter((dep) => dep !== id) })),
      }));
      if (selectedNodeId === id) {
        setSelectedNodeId(null);
      }
    },
    [selectedNodeId],
  );

  const handleNodeChange = useCallback((updatedNode: EditorNode) => {
    setState((prev) => {
      // Find the node we're editing by matching the selected node ID
      const editIdx = prev.nodes.findIndex((n) => n.id === selectedNodeId);
      if (editIdx === -1) return prev;

      const oldId = prev.nodes[editIdx].id;
      const newNodes = [...prev.nodes];
      newNodes[editIdx] = updatedNode;

      // If the node ID changed, update dependencies in other nodes
      if (oldId !== updatedNode.id) {
        for (let i = 0; i < newNodes.length; i++) {
          if (i !== editIdx && newNodes[i].depends_on.includes(oldId)) {
            newNodes[i] = {
              ...newNodes[i],
              depends_on: newNodes[i].depends_on.map((dep) => (dep === oldId ? updatedNode.id : dep)),
            };
          }
        }
      }

      return { ...prev, nodes: newNodes };
    });

    // Track the selected node by its new ID if it changed
    setSelectedNodeId(updatedNode.id);
  }, [selectedNodeId]);

  const handleYamlChange = useCallback((raw: string) => {
    try {
      const parsed = yamlToState(raw);
      setState(parsed);
      setParseError(null);
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "Invalid YAML");
    }
  }, []);

  async function handleSave() {
    const yamlStr = stateToYaml(state);
    try {
      const result = await createDefinition.mutateAsync({
        name: state.name,
        yaml_content: yamlStr,
        description: state.description || undefined,
        tags: state.tags.length > 0 ? state.tags : undefined,
      });
      onSave?.(result.id);
    } catch {
      // Mutation error is handled by TanStack Query
    }
  }

  return (
    <div className="space-y-4">
      {/* Action bar */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-200">
          {initialDefinition ? "Edit Workflow" : "New Workflow"}
        </h2>
        <div className="flex items-center gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="text-sm px-3 py-1.5 rounded bg-white/10 hover:bg-white/15 text-gray-400
                transition-colors"
            >
              Cancel
            </button>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={createDefinition.isPending || !state.name.trim()}
            className="text-sm px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white
              transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {createDefinition.isPending ? "Saving..." : "Save"}
          </button>
        </div>
      </div>

      {createDefinition.isError && (
        <div className="px-3 py-2 rounded bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {createDefinition.error instanceof Error ? createDefinition.error.message : "Failed to save workflow"}
        </div>
      )}

      {/* Split-pane layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-[500px]">
        {/* Left panel: form */}
        <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4 space-y-6 overflow-y-auto">
          <MetadataForm
            name={state.name}
            description={state.description}
            tags={state.tags}
            onChange={handleMetadataChange}
          />

          <div className="border-t border-white/5 pt-4">
            <NodeList
              nodes={state.nodes}
              selectedNodeId={selectedNodeId}
              onSelectNode={setSelectedNodeId}
              onAddNode={handleAddNode}
              onRemoveNode={handleRemoveNode}
            />
          </div>

          {selectedNode && (
            <div className="border-t border-white/5 pt-4">
              <NodeForm node={selectedNode} allNodeIds={allNodeIds} onChange={handleNodeChange} />
            </div>
          )}
        </div>

        {/* Right panel: YAML preview */}
        <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4">
          <YamlPanel yaml={yamlContent} onYamlChange={handleYamlChange} parseError={parseError} />
        </div>
      </div>
    </div>
  );
}
