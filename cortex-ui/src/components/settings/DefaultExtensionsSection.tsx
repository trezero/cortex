import { useAllExtensions, useSetExtensionDefault } from "@/features/projects/extensions/hooks/useExtensionQueries";
import type { Extension } from "@/features/projects/extensions/types";

const TYPE_LABELS: Record<string, string> = {
  skill: "Skills",
  command: "Commands",
  plugin: "Plugins",
};

const TYPE_COLORS: Record<string, string> = {
  skill: "text-cyan-400",
  command: "text-violet-400",
  plugin: "text-amber-400",
};

const TYPE_ORDER = ["skill", "command", "plugin"] as const;

function ExtensionRow({ ext }: { ext: Extension }) {
  const setDefault = useSetExtensionDefault();

  const handleToggle = () => {
    setDefault.mutate({ extensionId: ext.id, isDefault: !ext.is_default });
  };

  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-white/5 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{ext.display_name || ext.name}</p>
        {ext.description && (
          <p className="text-xs text-zinc-400 mt-0.5 truncate">{ext.description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={ext.is_default}
        onClick={handleToggle}
        disabled={setDefault.isPending}
        className={`flex-shrink-0 mt-0.5 relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 disabled:opacity-50 ${
          ext.is_default ? "bg-cyan-500" : "bg-zinc-700"
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
            ext.is_default ? "translate-x-4" : "translate-x-1"
          }`}
        />
      </button>
    </div>
  );
}

export function DefaultExtensionsSection() {
  const { data, isLoading, error } = useAllExtensions();

  if (isLoading) {
    return <p className="text-sm text-zinc-400">Loading extensions...</p>;
  }

  if (error) {
    return <p className="text-sm text-red-400">Failed to load extensions.</p>;
  }

  const extensions = data?.extensions ?? [];

  if (extensions.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        No extensions found. Extensions are synced from your Cortex registry.
      </p>
    );
  }

  const grouped: Record<string, Extension[]> = {};
  for (const ext of extensions) {
    const key = ext.type ?? "skill";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(ext);
  }

  const defaultCount = extensions.filter((e) => e.is_default).length;

  return (
    <div className="space-y-5">
      <p className="text-sm text-zinc-400">
        Extensions marked as default are installed on every new application registered via{" "}
        <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded">/cortex-setup</code>.{" "}
        <span className="text-zinc-500">{defaultCount} of {extensions.length} selected.</span>
      </p>

      {TYPE_ORDER.filter((t) => grouped[t]?.length).map((type) => (
        <div key={type}>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${TYPE_COLORS[type] ?? "text-zinc-400"}`}>
            {TYPE_LABELS[type] ?? type} ({grouped[type].length})
          </h4>
          <div>
            {grouped[type].map((ext) => (
              <ExtensionRow key={ext.id} ext={ext} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
