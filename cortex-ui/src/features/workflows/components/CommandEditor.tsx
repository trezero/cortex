import { useCallback, useMemo, useState } from "react";

import { useCommands, useCreateCommand, useDeleteCommand, useUpdateCommand } from "../hooks/useWorkflowQueries";
import type { WorkflowCommand } from "../types";

/**
 * Highlights variable placeholders ($ARGUMENTS, $1, $2, etc.) in a prompt template
 * by wrapping them in styled spans.
 */
function renderPreview(template: string): JSX.Element[] {
  const parts = template.split(/(\$[A-Z_]+|\$\d+)/g);
  return parts.map((part, i) => {
    if (/^\$[A-Z_]+$/.test(part) || /^\$\d+$/.test(part)) {
      return (
        <span key={i} className="px-1 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono text-sm">
          {part}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function CommandEditor() {
  const { data: commands, isLoading, error } = useCommands();
  const createCommand = useCreateCommand();
  const updateCommand = useUpdateCommand();
  const deleteCommand = useDeleteCommand();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Editor form state
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTemplate, setEditTemplate] = useState("");
  const [showPreview, setShowPreview] = useState(false);

  const selectedCommand = useMemo(
    () => commands?.find((c) => c.id === selectedId) ?? null,
    [commands, selectedId],
  );

  const handleSelectCommand = useCallback(
    (command: WorkflowCommand) => {
      setSelectedId(command.id);
      setEditName(command.name);
      setEditDescription(command.description ?? "");
      setEditTemplate(command.prompt_template);
      setIsCreating(false);
      setShowPreview(false);
    },
    [],
  );

  const handleNewCommand = useCallback(() => {
    setSelectedId(null);
    setEditName("");
    setEditDescription("");
    setEditTemplate("");
    setIsCreating(true);
    setShowPreview(false);
  }, []);

  const handleSave = useCallback(async () => {
    if (!editName.trim() || !editTemplate.trim()) return;

    try {
      if (isCreating) {
        const result = await createCommand.mutateAsync({
          name: editName.trim(),
          prompt_template: editTemplate,
          description: editDescription.trim() || undefined,
        });
        setSelectedId(result.id);
        setIsCreating(false);
      } else if (selectedId) {
        await updateCommand.mutateAsync({
          id: selectedId,
          data: {
            name: editName.trim(),
            prompt_template: editTemplate,
            description: editDescription.trim() || undefined,
          },
        });
      }
    } catch {
      // Mutation error handled by TanStack Query
    }
  }, [isCreating, selectedId, editName, editTemplate, editDescription, createCommand, updateCommand]);

  const handleDelete = useCallback(async () => {
    if (!selectedId) return;
    try {
      await deleteCommand.mutateAsync(selectedId);
      setSelectedId(null);
      setEditName("");
      setEditDescription("");
      setEditTemplate("");
    } catch {
      // Mutation error handled by TanStack Query
    }
  }, [selectedId, deleteCommand]);

  const isSaving = createCommand.isPending || updateCommand.isPending;
  const isDeleting = deleteCommand.isPending;
  const hasChanges = isCreating || (
    selectedCommand &&
    (editName !== selectedCommand.name ||
      editTemplate !== selectedCommand.prompt_template ||
      (editDescription || null) !== (selectedCommand.description || null))
  );

  if (isLoading) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-gray-400 text-sm">Loading commands...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-6">
        <div className="text-red-400 text-sm">
          Failed to load commands: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-[500px]">
      {/* Left panel: command list */}
      <div className="bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-200">
            Command Library
            {commands?.length ? (
              <span className="ml-2 text-xs text-cyan-400">({commands.length})</span>
            ) : null}
          </h3>
          <button
            type="button"
            onClick={handleNewCommand}
            className="text-xs px-2 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
          >
            + New
          </button>
        </div>

        <div className="divide-y divide-white/5 overflow-y-auto flex-1">
          {!commands?.length && !isCreating ? (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">
              No commands yet. Create one to get started.
            </div>
          ) : null}

          {commands?.map((command) => (
            <button
              key={command.id}
              type="button"
              onClick={() => handleSelectCommand(command)}
              className={`w-full text-left px-4 py-3 transition-colors hover:bg-white/5 ${
                selectedId === command.id ? "bg-white/10 border-l-2 border-l-cyan-500" : ""
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-200 truncate">{command.name}</span>
                {command.is_builtin && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400">
                    built-in
                  </span>
                )}
              </div>
              {command.description && (
                <div className="text-xs text-gray-500 truncate">{command.description}</div>
              )}
              <div className="text-xs text-gray-600 mt-1">{formatTimestamp(command.created_at)}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel: editor + preview */}
      <div className="lg:col-span-2 bg-gray-900/80 backdrop-blur-md border border-white/10 rounded-lg p-4 flex flex-col">
        {!selectedId && !isCreating ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
            Select a command or create a new one
          </div>
        ) : (
          <>
            {/* Editor header */}
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-200">
                {isCreating ? "New Command" : "Edit Command"}
              </h3>
              <div className="flex items-center gap-2">
                {selectedId && !isCreating && (
                  <button
                    type="button"
                    onClick={handleDelete}
                    disabled={isDeleting || selectedCommand?.is_builtin}
                    className="text-xs px-2 py-1 rounded bg-red-500/10 hover:bg-red-500/20 text-red-400
                      transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isDeleting ? "Deleting..." : "Delete"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowPreview(!showPreview)}
                  className={`text-xs px-2 py-1 rounded transition-colors ${
                    showPreview
                      ? "bg-cyan-600/20 text-cyan-400"
                      : "bg-white/10 hover:bg-white/15 text-gray-400"
                  }`}
                >
                  {showPreview ? "Editor" : "Preview"}
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving || !editName.trim() || !editTemplate.trim() || !hasChanges}
                  className="text-xs px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white
                    transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSaving ? "Saving..." : "Save"}
                </button>
              </div>
            </div>

            {/* Mutation errors */}
            {(createCommand.isError || updateCommand.isError || deleteCommand.isError) && (
              <div className="mb-3 px-3 py-2 rounded bg-red-500/10 border border-red-500/30 text-sm text-red-400">
                {(() => {
                  const err = createCommand.error || updateCommand.error || deleteCommand.error;
                  return err instanceof Error ? err.message : "Operation failed";
                })()}
              </div>
            )}

            {/* Name + description fields */}
            <div className="space-y-3 mb-4">
              <div>
                <label htmlFor="cmd-name" className="block text-xs text-gray-400 mb-1">
                  Name
                </label>
                <input
                  id="cmd-name"
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="e.g. implement-feature"
                  className="w-full px-3 py-1.5 rounded bg-white/5 border border-white/10 text-sm text-gray-200
                    placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors"
                />
              </div>
              <div>
                <label htmlFor="cmd-desc" className="block text-xs text-gray-400 mb-1">
                  Description
                </label>
                <input
                  id="cmd-desc"
                  type="text"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="Short description of what this command does"
                  className="w-full px-3 py-1.5 rounded bg-white/5 border border-white/10 text-sm text-gray-200
                    placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors"
                />
              </div>
            </div>

            {/* Prompt template editor / preview */}
            <div className="flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs text-gray-400">
                  Prompt Template
                </label>
                <span className="text-xs text-gray-600">
                  Use <code className="text-cyan-500/70">$ARGUMENTS</code>,{" "}
                  <code className="text-cyan-500/70">$1</code>,{" "}
                  <code className="text-cyan-500/70">$2</code> for placeholders
                </span>
              </div>

              {showPreview ? (
                <div
                  className="flex-1 overflow-y-auto rounded bg-white/5 border border-white/10 p-4
                    text-sm text-gray-300 whitespace-pre-wrap leading-relaxed"
                >
                  {editTemplate ? (
                    renderPreview(editTemplate)
                  ) : (
                    <span className="text-gray-600">No template content to preview</span>
                  )}
                </div>
              ) : (
                <textarea
                  value={editTemplate}
                  onChange={(e) => setEditTemplate(e.target.value)}
                  placeholder={`You are an expert software engineer.\n\nImplement the following feature: $ARGUMENTS\n\nRequirements:\n- $1\n- $2`}
                  className="flex-1 w-full px-3 py-2 rounded bg-white/5 border border-white/10 text-sm text-gray-200
                    placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors
                    font-mono resize-none min-h-[200px]"
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
