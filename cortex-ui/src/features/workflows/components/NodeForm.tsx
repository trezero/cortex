import type { EditorNode } from "../types";
import { DependencySelect } from "./editor/DependencySelect";

interface NodeFormProps {
  node: EditorNode;
  allNodeIds: string[];
  onChange: (updatedNode: EditorNode) => void;
}

export function NodeForm({ node, allNodeIds, onChange }: NodeFormProps) {
  const availableDeps = allNodeIds.filter((id) => id !== node.id);

  function update(field: keyof EditorNode, value: string | string[] | boolean) {
    onChange({ ...node, [field]: value });
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-gray-400">Edit Node</h3>

      <div>
        <label htmlFor="node-id" className="block text-sm text-gray-400 mb-1">
          Node ID
        </label>
        <input
          id="node-id"
          type="text"
          value={node.id}
          onChange={(e) => update("id", e.target.value)}
          placeholder="build-step"
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors"
        />
      </div>

      <div>
        <label htmlFor="node-command" className="block text-sm text-gray-400 mb-1">
          Command
        </label>
        <input
          id="node-command"
          type="text"
          value={node.command}
          onChange={(e) => update("command", e.target.value)}
          placeholder="claude-code"
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors"
        />
      </div>

      <div>
        <label htmlFor="node-prompt" className="block text-sm text-gray-400 mb-1">
          Prompt
        </label>
        <textarea
          id="node-prompt"
          value={node.prompt}
          onChange={(e) => update("prompt", e.target.value)}
          placeholder="Describe the task for this node..."
          rows={4}
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors resize-none"
        />
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">Dependencies</label>
        <DependencySelect
          selectedIds={node.depends_on}
          availableIds={availableDeps}
          onChange={(ids) => update("depends_on", ids)}
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          id="node-approval"
          type="checkbox"
          checked={node.approval_required}
          onChange={(e) => update("approval_required", e.target.checked)}
          className="accent-cyan-500"
        />
        <label htmlFor="node-approval" className="text-sm text-gray-400">
          Approval required
        </label>
      </div>

      <div>
        <label htmlFor="node-when" className="block text-sm text-gray-400 mb-1">
          When condition <span className="text-gray-600">(optional)</span>
        </label>
        <input
          id="node-when"
          type="text"
          value={node.when ?? ""}
          onChange={(e) => update("when", e.target.value)}
          placeholder="previous.exit_code == 0"
          className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-gray-200
            placeholder:text-gray-600 focus:border-cyan-500 focus:outline-none transition-colors"
        />
      </div>
    </div>
  );
}
