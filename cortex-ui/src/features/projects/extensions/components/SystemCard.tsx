import type { SystemWithExtensions } from "../types";

interface SystemCardProps {
  system: SystemWithExtensions;
  isSelected: boolean;
  onClick: () => void;
  onUnlink: (systemId: string) => void;
}

export function SystemCard({ system, isSelected, onClick, onUnlink }: SystemCardProps) {
  const isOnline = isRecentlyActive(system.last_seen_at);
  const extensionCount = system.extensions?.length ?? 0;

  return (
    <div
      className={`rounded-lg border transition-colors ${
        isSelected
          ? "border-cyan-500/50 bg-cyan-500/10"
          : "border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/[0.07]"
      }`}
    >
      <button type="button" onClick={onClick} className="w-full text-left p-3">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isOnline ? "bg-emerald-400" : "bg-zinc-500"}`} />
          <span className="font-medium text-sm text-white truncate">{system.name}</span>
        </div>
        <div className="mt-1 text-xs text-zinc-400">
          {extensionCount} extension{extensionCount !== 1 ? "s" : ""}
          {system.hostname && ` · ${system.hostname}`}
        </div>
      </button>
      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onUnlink(system.id);
          }}
          className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
        >
          Unlink from project
        </button>
      </div>
    </div>
  );
}

function isRecentlyActive(lastSeen: string): boolean {
  const fiveMinutes = 5 * 60 * 1000;
  return Date.now() - new Date(lastSeen).getTime() < fiveMinutes;
}
