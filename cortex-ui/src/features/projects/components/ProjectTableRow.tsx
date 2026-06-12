import { FolderTree, Zap } from "lucide-react";
import { cn } from "../../ui/primitives/styles";
import type { Project } from "../types";
import { SystemBadge } from "./SystemBadge";

interface TaskCounts {
  todo: number;
  doing: number;
  done: number;
}

interface ProjectTableRowProps {
  project: Project;
  taskCounts?: TaskCounts;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onTogglePin?: (id: string, pinned: boolean) => void;
  childCount?: number;
  parentTitle?: string;
  onSelectParent?: (parentId: string) => void;
}

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

export function ProjectTableRow({
  project,
  taskCounts,
  isSelected,
  onSelect,
  onTogglePin,
  childCount,
  parentTitle,
  onSelectParent,
}: ProjectTableRowProps) {
  const registrations = project.system_registrations ?? [];
  const primaryReg = registrations[0];
  const extraCount = registrations.length - 1;

  const dirtySystems = registrations.filter((r) => r.git_dirty);
  const dirtyLabel = dirtySystems.map((r) => r.system_name).join(", ");

  const tags = project.tags ?? [];
  const visibleTags = tags.slice(0, 2);
  const extraTagCount = tags.length - 2;

  const rowClass = [
    "flex items-center gap-2 px-4 py-2.5 border-b cursor-pointer transition-colors focus:outline-none focus:ring-1 focus:ring-purple-500/30",
    isSelected ? "bg-purple-600/10 border-purple-500/20" : "border-white/5 hover:bg-white/[0.03]",
  ].join(" ");

  return (
    <div
      className={rowClass}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(project.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSelect(project.id);
      }}
    >
      {/* Status column (~w-12) */}
      <div className="w-12 flex-shrink-0 flex items-center gap-1">
        <button
          type="button"
          className={cn(
            "shrink-0 transition-all duration-200",
            project.pinned
              ? "text-amber-400 drop-shadow-[0_0_6px_rgba(251,191,36,0.6)]"
              : "text-gray-700 hover:text-gray-400",
          )}
          title={project.pinned ? "Unpin project" : "Pin project"}
          aria-label={project.pinned ? "Unpin project" : "Pin project"}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin?.(project.id, !project.pinned);
          }}
        >
          <Zap className={cn("w-3.5 h-3.5", project.pinned && "fill-amber-400")} />
        </button>
        {project.has_uncommitted_changes && (
          <span
            className="w-[7px] h-[7px] rounded-full bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.5)]"
            aria-label={`Uncommitted changes on: ${dirtyLabel}`}
          />
        )}
      </div>

      {/* Project column (flex-1) */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {childCount !== undefined && childCount > 0 && (
            <FolderTree className="w-3 h-3 text-gray-500 shrink-0" aria-hidden="true" />
          )}
          <span className="text-sm text-[#c0c0d8] truncate">{project.title}</span>
          {childCount !== undefined && childCount > 0 && (
            <span className="text-[10px] text-gray-600 shrink-0">{childCount} sub</span>
          )}
        </div>
        {parentTitle && project.parent_project_id && (
          <button
            type="button"
            className="text-[11px] text-gray-500 hover:text-cyan-400 transition-colors truncate block"
            onClick={(e) => {
              e.stopPropagation();
              if (project.parent_project_id) {
                onSelectParent?.(project.parent_project_id);
              }
            }}
          >
            ↳ {parentTitle}
          </button>
        )}
      </div>

      {/* System column (~w-36) */}
      <div className="w-36 flex-shrink-0 flex items-center gap-1">
        {primaryReg ? (
          <>
            <SystemBadge name={primaryReg.system_name} os={primaryReg.os} />
            {extraCount > 0 && <span className="text-[10px] text-gray-600">+{extraCount}</span>}
          </>
        ) : null}
      </div>

      {/* Todo column (~w-16) */}
      <div className="w-16 flex-shrink-0 text-center text-sm">
        {taskCounts && taskCounts.todo > 0 ? (
          <span className="text-[#f472b6]">{taskCounts.todo}</span>
        ) : (
          <span className="text-gray-700">—</span>
        )}
      </div>

      {/* Doing column (~w-16) */}
      <div className="w-16 flex-shrink-0 text-center text-sm">
        {taskCounts && taskCounts.doing > 0 ? (
          <span className="text-[#93c5fd]">{taskCounts.doing}</span>
        ) : (
          <span className="text-gray-700">—</span>
        )}
      </div>

      {/* Done column (~w-16) */}
      <div className="w-16 flex-shrink-0 text-center text-sm">
        {taskCounts && taskCounts.done > 0 ? (
          <span className="text-[#86efac]">{taskCounts.done}</span>
        ) : (
          <span className="text-gray-700">—</span>
        )}
      </div>

      {/* Tags column (~w-32) */}
      <div className="w-32 flex-shrink-0 flex items-center gap-1 flex-wrap">
        {visibleTags.map((t) => (
          <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-gray-500">
            {t}
          </span>
        ))}
        {extraTagCount > 0 && <span className="text-[10px] text-gray-600">+{extraTagCount}</span>}
      </div>

      {/* Activity column (~w-28) */}
      <div className="w-28 flex-shrink-0 text-right text-[11px] text-gray-500">
        {formatRelativeTime(project.updated_at)}
      </div>
    </div>
  );
}
