import { DataCard, DataCardContent } from "../../ui/primitives/data-card";
import { cn } from "../../ui/primitives/styles";
import type { ChildProject } from "../types";
import { resolveEdgeColor, SystemBadge } from "./SystemBadge";

interface SubProjectCardProps {
  project: ChildProject;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

export function SubProjectCard({ project, isSelected, onSelect }: SubProjectCardProps) {
  const registrations = project.system_registrations ?? [];
  const primaryReg = registrations[0];
  const systemEdgeColor = primaryReg ? resolveEdgeColor(primaryReg.system_name) : "cyan";
  const edgeColor = isSelected ? "purple" : systemEdgeColor;

  const hasDirty = registrations.some((r) => r.git_dirty);

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "shrink-0 w-52 cursor-pointer transition-transform duration-200",
        isSelected && "scale-[1.01]",
        !isSelected && "hover:scale-[1.02] hover:shadow-[0_0_15px_rgba(6,182,212,0.15)]",
      )}
      onClick={() => onSelect(project.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(project.id);
        }
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
        )}
      >
        <DataCardContent className="px-3 py-2.5 space-y-1.5">
          {/* Project name */}
          <span className="text-sm font-medium text-white/80 truncate block">{project.title}</span>

          {/* System badges + dirty indicator */}
          <div className="flex items-center gap-1.5">
            {primaryReg && <SystemBadge name={primaryReg.system_name} os={primaryReg.os} />}
            {registrations.length > 1 && <span className="text-[10px] text-gray-500">+{registrations.length - 1}</span>}
            {hasDirty && (
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full bg-amber-500 ml-auto shrink-0",
                  "shadow-[0_0_4px_rgba(245,158,11,0.5)]",
                )}
                aria-label="Uncommitted changes"
              />
            )}
          </div>
        </DataCardContent>
      </DataCard>
    </div>
  );
}
