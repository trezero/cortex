import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../../ui/primitives/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../ui/primitives/dialog";
import { Input } from "../../ui/primitives/input";
import { cn } from "../../ui/primitives/styles";
import { useProjectChildren, useProjects, useSetParentProject } from "../hooks/useProjectQueries";
import type { Project } from "../types";

interface ManageSubProjectsModalProps {
  parentProjectId: string;
  parentTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ManageSubProjectsModal({
  parentProjectId,
  parentTitle,
  open,
  onOpenChange,
}: ManageSubProjectsModalProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const { data: children = [] } = useProjectChildren(parentProjectId);
  const { data: allProjects = [] } = useProjects();
  const setParentMutation = useSetParentProject();

  // Candidates: projects that can be added as children
  // - Not the parent itself
  // - Don't already have a parent (single-parent constraint)
  // - Not already a child of this parent
  const candidates = useMemo(() => {
    const childIds = new Set(children.map((c) => c.id));
    const query = searchQuery.toLowerCase().trim();
    return (allProjects as Project[]).filter((p) => {
      if (p.id === parentProjectId) return false;
      if (p.parent_project_id) return false;
      if (childIds.has(p.id)) return false;
      if (query && !p.title.toLowerCase().includes(query)) return false;
      return true;
    });
  }, [allProjects, parentProjectId, children, searchQuery]);

  const handleLink = (projectId: string) => {
    setParentMutation.mutate({
      projectId,
      parentProjectId: parentProjectId,
    });
  };

  const handleUnlink = (projectId: string) => {
    setParentMutation.mutate({
      projectId,
      parentProjectId: null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle
            className={cn(
              "text-lg font-bold",
              "bg-gradient-to-r from-cyan-400 to-blue-500",
              "text-transparent bg-clip-text",
            )}
          >
            Manage Sub-Projects — {parentTitle}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Current children */}
          <div>
            <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
              Current Sub-Projects ({children.length})
            </h4>
            {children.length === 0 ? (
              <p className="text-sm text-gray-600">No sub-projects linked.</p>
            ) : (
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {children.map((child) => (
                  <div
                    key={child.id}
                    className={cn(
                      "flex items-center justify-between px-3 py-2 rounded-lg",
                      "bg-white/5 border border-white/5",
                    )}
                  >
                    <span className="text-sm text-gray-300 truncate">{child.title}</span>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => handleUnlink(child.id)}
                      disabled={setParentMutation.isPending}
                      aria-label={`Unlink ${child.title}`}
                    >
                      <X className="w-3.5 h-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Search to add */}
          <div>
            <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Add Projects</h4>
            <div className="relative mb-2">
              <Search
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500"
                aria-hidden="true"
              />
              <Input
                placeholder="Search projects..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-8 text-sm"
              />
            </div>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {candidates.length === 0 ? (
                <p className="text-sm text-gray-600 py-2">
                  {searchQuery ? "No matching projects" : "No available projects"}
                </p>
              ) : (
                candidates.slice(0, 20).map((project) => (
                  <button
                    key={project.id}
                    type="button"
                    className={cn(
                      "flex w-full items-center justify-between px-3 py-2 rounded-lg",
                      "hover:bg-white/5 transition-colors cursor-pointer",
                      "bg-transparent border-0",
                    )}
                    onClick={() => handleLink(project.id)}
                  >
                    <span className="text-sm text-gray-300 truncate">{project.title}</span>
                    <span className="text-[10px] text-cyan-500 shrink-0 ml-2">+ Add</span>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
