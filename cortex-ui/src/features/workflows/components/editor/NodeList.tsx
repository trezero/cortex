import type { EditorNode } from "../../types";

interface NodeListProps {
  nodes: EditorNode[];
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
  onAddNode: () => void;
  onRemoveNode: (id: string) => void;
}

export function NodeList({ nodes, selectedNodeId, onSelectNode, onAddNode, onRemoveNode }: NodeListProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-400">Nodes</h3>
        <button
          type="button"
          onClick={onAddNode}
          className="text-xs px-2 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
        >
          + Add Node
        </button>
      </div>

      {nodes.length === 0 && (
        <p className="text-xs text-gray-600 italic py-2">No nodes yet. Add one to get started.</p>
      )}

      <div className="space-y-1">
        {nodes.map((node) => {
          const isSelected = node.id === selectedNodeId;
          return (
            <div
              key={node.id}
              className={`flex items-center gap-2 rounded px-3 py-2 cursor-pointer transition-colors border ${
                isSelected
                  ? "bg-cyan-500/10 border-cyan-500/40"
                  : "bg-white/5 border-white/10 hover:border-cyan-500/20"
              }`}
            >
              <button
                type="button"
                onClick={() => onSelectNode(node.id)}
                className="flex-1 min-w-0 text-left"
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-sm font-mono text-gray-200 truncate">{node.id}</span>
                  {node.approval_required && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 shrink-0">
                      approval
                    </span>
                  )}
                </div>
                <span className="text-xs text-gray-500 truncate block">{node.command || "no command"}</span>
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveNode(node.id);
                }}
                title="Remove node"
                className="text-gray-600 hover:text-red-400 transition-colors text-sm px-1 shrink-0"
              >
                x
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
