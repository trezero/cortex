import type { Extension, SystemExtension } from "../types";
import { ExtensionStatusBadge } from "./ExtensionStatusBadge";

interface SystemExtensionListProps {
  systemExtensions: SystemExtension[];
  allExtensions: Extension[];
  onInstall: (extensionId: string) => void;
  onRemove: (extensionId: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  skill: "Skills",
  command: "Commands",
  plugin: "Plugins",
};

const TYPE_ORDER: string[] = ["skill", "command", "plugin"];

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    skill: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
    command: "bg-violet-500/20 text-violet-400 border-violet-500/30",
    plugin: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  };
  return (
    <span
      className={`px-1.5 py-0.5 text-[10px] rounded border ${colors[type] ?? "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"}`}
    >
      {type}
    </span>
  );
}

function groupByType<T extends { type?: string }>(items: T[]): Record<string, T[]> {
  const groups: Record<string, T[]> = {};
  for (const item of items) {
    const type = item.type ?? "skill";
    if (!groups[type]) groups[type] = [];
    groups[type].push(item);
  }
  return groups;
}

export function SystemExtensionList({
  systemExtensions,
  allExtensions,
  onInstall,
  onRemove,
}: SystemExtensionListProps) {
  const installedExtensionIds = new Set(systemExtensions.map((se) => se.extension_id));
  const availableExtensions = allExtensions.filter((e) => !installedExtensionIds.has(e.id));

  // Group installed by type (via joined extension data)
  const installedByType: Record<string, SystemExtension[]> = {};
  for (const se of systemExtensions) {
    const type = se.cortex_extensions?.type ?? "skill";
    if (!installedByType[type]) installedByType[type] = [];
    installedByType[type].push(se);
  }

  const availableByType = groupByType(availableExtensions);

  const hasInstalled = systemExtensions.length > 0;
  const hasAvailable = availableExtensions.length > 0;

  return (
    <div className="space-y-4">
      {hasInstalled && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Installed Extensions</h4>
          <div className="space-y-3">
            {TYPE_ORDER.filter((t) => installedByType[t]?.length).map((type) => (
              <div key={type}>
                <div className="text-[11px] text-zinc-500 font-medium mb-1">{TYPE_LABELS[type] ?? type}</div>
                <div className="space-y-1">
                  {installedByType[type].map((se) => (
                    <div key={se.id} className="flex items-center justify-between p-2 rounded-md bg-white/5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white">
                          {se.cortex_extensions?.display_name || se.cortex_extensions?.name || se.extension_id}
                        </span>
                        <TypeBadge type={type} />
                      </div>
                      <div className="flex items-center gap-2">
                        <ExtensionStatusBadge status={se.status} hasLocalChanges={se.has_local_changes} />
                        <button
                          type="button"
                          onClick={() => onRemove(se.extension_id)}
                          className="px-2 py-1 text-xs rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {hasAvailable && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Available</h4>
          <div className="space-y-3">
            {TYPE_ORDER.filter((t) => availableByType[t]?.length).map((type) => (
              <div key={type}>
                <div className="text-[11px] text-zinc-500 font-medium mb-1">{TYPE_LABELS[type] ?? type}</div>
                <div className="space-y-1">
                  {availableByType[type].map((extension) => (
                    <div key={extension.id} className="flex items-center justify-between p-2 rounded-md bg-white/5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white">{extension.display_name || extension.name}</span>
                        <TypeBadge type={type} />
                        {extension.is_required && <span className="text-xs text-cyan-400">Required</span>}
                      </div>
                      <button
                        type="button"
                        onClick={() => onInstall(extension.id)}
                        className="px-3 py-1 text-xs rounded-md bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors"
                      >
                        Install
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasInstalled && !hasAvailable && (
        <div className="text-center py-8 text-zinc-500 text-sm">
          No extensions in the registry yet. Extensions are added when systems sync.
        </div>
      )}
    </div>
  );
}
