import { Settings2 } from "lucide-react";
import { Button } from "../../ui/primitives/button";
import { cn } from "../../ui/primitives/styles";
import { useProjectChildren } from "../hooks/useProjectQueries";
import { SubProjectCard } from "./SubProjectCard";

interface SubProjectsStripProps {
  parentProjectId: string;
  selectedProjectId?: string;
  onSelectProject: (id: string) => void;
  onManage: () => void;
}

export function SubProjectsStrip({ parentProjectId, selectedProjectId, onSelectProject, onManage }: SubProjectsStripProps) {
  const { data: children, isLoading, error } = useProjectChildren(parentProjectId);

  // Hide strip entirely when no children and not loading
  if (!isLoading && !error && (!children || children.length === 0)) {
    return null;
  }

  return (
    <div className="border-b border-white/5 pb-3 mb-1">
      {/* Strip header */}
      <div className="flex items-center justify-between px-4 mb-2">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Sub-Projects</span>
        <Button variant="ghost" size="xs" onClick={onManage} aria-label="Manage sub-projects">
          <Settings2 className="w-3.5 h-3.5 mr-1" aria-hidden="true" />
          Manage
        </Button>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="px-4">
          <div className="h-16 rounded-lg bg-white/5 animate-pulse" />
        </div>
      )}

      {/* Error state */}
      {error && <div className="px-4 text-xs text-red-400/70">Failed to load sub-projects</div>}

      {/* Cards strip */}
      {children && children.length > 0 && (
        <div className="w-full px-4">
          <div className={cn("overflow-x-auto scrollbar-hide")}>
            <div className="flex gap-2 min-w-max">
              {children.map((child) => (
                <SubProjectCard key={child.id} project={child} isSelected={child.id === selectedProjectId} onSelect={onSelectProject} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
