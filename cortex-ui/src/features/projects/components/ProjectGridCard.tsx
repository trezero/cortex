import { Clock, FolderTree, Zap } from "lucide-react";
import { DataCard, DataCardContent, DataCardHeader } from "../../ui/primitives/data-card";
import { StatPill } from "../../ui/primitives/pill";
import { cn } from "../../ui/primitives/styles";
import type { Project } from "../types";
import { resolveEdgeColor, SystemBadge } from "./SystemBadge";

interface TaskCounts {
  todo: number;
  doing: number;
  done: number;
}

interface ProjectGridCardProps {
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
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

export function ProjectGridCard({
  project,
  taskCounts,
  isSelected,
  onSelect,
  onTogglePin,
  childCount,
  parentTitle,
  onSelectParent,
}: ProjectGridCardProps) {
  const registrations = project.system_registrations ?? [];
  const primaryReg = registrations[0];
  const extraCount = registrations.length - 1;

  const dirtySystems = registrations.filter((r) => r.git_dirty);
  const dirtyTitle = dirtySystems.map((r) => r.system_name).join(", ");

  // Always derive edge color from the primary system name.
  // Selected state gets purple overlay; otherwise use the system-derived color.
  const systemEdgeColor = primaryReg ? resolveEdgeColor(primaryReg.system_name) : "cyan";
  const edgeColor = isSelected ? "purple" : systemEdgeColor;

  const parentId = project.parent_project_id;

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "relative group cursor-pointer transition-transform duration-200 hover:scale-[1.02]",
        isSelected && "scale-[1.01]",
      )}
      onClick={() => onSelect(project.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSelect(project.id);
      }}
    >
      <DataCard
        edgePosition="top"
        edgeColor={edgeColor}
        blur="md"
        compact
        className={cn(
          "transition-shadow",
          isSelected && "shadow-[0_0_25px_rgba(139,92,246,0.25)]",
          !isSelected && "hover:shadow-[0_0_20px_rgba(6,182,212,0.15)]",
        )}
      >
        <DataCardHeader className="p-4 pb-2">
          {/* Pin toggle + Title */}
          <div className="flex items-start gap-2">
            <button
              type="button"
              className={cn(
                "mt-0.5 shrink-0 transition-all duration-200",
                project.pinned
                  ? "text-amber-400 drop-shadow-[0_0_6px_rgba(251,191,36,0.6)]"
                  : "text-gray-600 opacity-0 group-hover:opacity-100 hover:text-gray-400",
              )}
              style={
                project.pinned
                  ? {
                      filter: "drop-shadow(0 0 4px rgba(251,191,36,0.5))",
                    }
                  : undefined
              }
              title={project.pinned ? "Unpin project" : "Pin project"}
              aria-label={project.pinned ? "Unpin project" : "Pin project"}
              onClick={(e) => {
                e.stopPropagation();
                onTogglePin?.(project.id, !project.pinned);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  onTogglePin?.(project.id, !project.pinned);
                }
              }}
            >
              <Zap className={cn("w-4 h-4", project.pinned && "fill-amber-400")} />
            </button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                {childCount !== undefined && childCount > 0 && (
                  <FolderTree className="w-3.5 h-3.5 text-gray-400 shrink-0" aria-hidden="true" />
                )}
                <span
                  className={cn(
                    "text-base font-semibold leading-tight line-clamp-2",
                    isSelected ? "text-white/90" : "text-white/80",
                  )}
                >
                  {project.title}
                </span>
              </div>
              {parentTitle && parentId && (
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:text-cyan-400 transition-colors truncate block mt-0.5"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectParent?.(parentId);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onSelectParent?.(parentId);
                    }
                  }}
                >
                  ↳ {parentTitle}
                </button>
              )}
            </div>
          </div>
        </DataCardHeader>

        <DataCardContent className="px-4 pb-4 space-y-2.5">
          {/* System row */}
          {primaryReg && (
            <div className="flex items-center gap-1.5">
              <SystemBadge name={primaryReg.system_name} os={primaryReg.os} />
              {extraCount > 0 && <span className="text-xs text-gray-500">+{extraCount}</span>}
              {project.has_uncommitted_changes && (
                <span
                  className="w-2 h-2 rounded-full bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.5)] ml-auto shrink-0"
                  title={dirtyTitle}
                  aria-label={`Uncommitted changes on: ${dirtyTitle}`}
                />
              )}
            </div>
          )}

          {/* Task pills row */}
          {taskCounts && (taskCounts.todo > 0 || taskCounts.doing > 0 || taskCounts.done > 0) && (
            <div className="flex gap-1.5 flex-wrap">
              {taskCounts.todo > 0 && <StatPill color="pink" value={`${taskCounts.todo} todo`} size="sm" />}
              {taskCounts.doing > 0 && <StatPill color="blue" value={`${taskCounts.doing} doing`} size="sm" />}
              {taskCounts.done > 0 && <StatPill color="green" value={`${taskCounts.done} done`} size="sm" />}
            </div>
          )}

          {/* Sub-project count */}
          {childCount !== undefined && childCount > 0 && (
            <StatPill color="gray" value={`${childCount} sub`} size="sm" />
          )}

          {/* Activity timestamp */}
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <Clock className="w-3 h-3" />
            {formatRelativeTime(project.updated_at)}
          </div>
        </DataCardContent>
      </DataCard>
    </div>
  );
}
