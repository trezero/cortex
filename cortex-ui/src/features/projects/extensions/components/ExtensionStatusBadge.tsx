interface ExtensionStatusBadgeProps {
  status: "pending_install" | "installed" | "pending_remove" | "removed";
  hasLocalChanges?: boolean;
}

const STATUS_CONFIG = {
  installed: { label: "Installed", className: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  pending_install: { label: "Pending Install", className: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" },
  pending_remove: { label: "Pending Remove", className: "bg-red-500/20 text-red-400 border-red-500/30" },
  removed: { label: "Removed", className: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30" },
  local_changes: { label: "Local Changes", className: "bg-orange-500/20 text-orange-400 border-orange-500/30" },
};

export function ExtensionStatusBadge({ status, hasLocalChanges }: ExtensionStatusBadgeProps) {
  const effectiveStatus = hasLocalChanges && status === "installed" ? "local_changes" : status;
  const config = STATUS_CONFIG[effectiveStatus];

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${config.className}`}
    >
      {config.label}
    </span>
  );
}
