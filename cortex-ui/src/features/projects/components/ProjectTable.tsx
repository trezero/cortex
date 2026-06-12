import { useState } from "react";
import type { SortColumn, SortState } from "../hooks/useProjectFilters";
import type { Project } from "../types";
import { ProjectTableRow } from "./ProjectTableRow";

interface TaskCountMap {
  [projectId: string]: { todo: number; doing: number; done: number } | undefined;
}

interface ProjectTableProps {
  projects: Project[];
  allProjects: Project[];
  taskCounts: TaskCountMap;
  selectedProjectId?: string;
  onSelectProject: (id: string) => void;
  onTogglePin?: (id: string, pinned: boolean) => void;
  sort: SortState;
  toggleSort: (column: SortColumn) => void;
  groupByParent: boolean;
}

function SortIndicator({ column, sort }: { column: SortColumn; sort: SortState }) {
  if (sort.column !== column) return null;
  return <span className="ml-0.5">{sort.direction === "asc" ? "↑" : "↓"}</span>;
}

const HEADER_BASE =
  "flex items-center gap-2 px-4 py-2 border-b border-white/10 text-[11px] text-gray-500 uppercase tracking-wider font-medium";

export function ProjectTable({
  projects,
  allProjects,
  taskCounts,
  selectedProjectId,
  onSelectProject,
  onTogglePin,
  sort,
  toggleSort,
  groupByParent,
}: ProjectTableProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const childCountMap = new Map<string, number>();
  for (const p of allProjects) {
    if (p.parent_project_id) {
      childCountMap.set(p.parent_project_id, (childCountMap.get(p.parent_project_id) ?? 0) + 1);
    }
  }
  const projectTitleMap = new Map(allProjects.map((p) => [p.id, p.title]));

  if (projects.length === 0) {
    return <div className="flex items-center justify-center h-40 text-gray-500 text-sm">No projects found</div>;
  }

  const toggleCollapse = (parentId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(parentId)) {
        next.delete(parentId);
      } else {
        next.add(parentId);
      }
      return next;
    });
  };

  const renderRow = (project: Project) => (
    <ProjectTableRow
      key={project.id}
      project={project}
      taskCounts={taskCounts[project.id]}
      isSelected={selectedProjectId === project.id}
      onSelect={onSelectProject}
      onTogglePin={onTogglePin}
      childCount={childCountMap.get(project.id)}
      parentTitle={project.parent_project_id ? projectTitleMap.get(project.parent_project_id) : undefined}
      onSelectParent={onSelectProject}
    />
  );

  const renderGrouped = () => {
    const parentMap = new Map<string, Project[]>();
    const roots: Project[] = [];

    for (const p of projects) {
      if (p.parent_project_id) {
        const children = parentMap.get(p.parent_project_id) ?? [];
        children.push(p);
        parentMap.set(p.parent_project_id, children);
      } else {
        roots.push(p);
      }
    }

    const rows: React.ReactNode[] = [];

    for (const parent of roots) {
      rows.push(renderRow(parent));

      const children = parentMap.get(parent.id);
      if (children && children.length > 0) {
        const isCollapsed = collapsed.has(parent.id);

        rows.push(
          <div
            key={`group-${parent.id}`}
            role="button"
            tabIndex={0}
            aria-expanded={!isCollapsed}
            className="flex items-center gap-2 px-4 py-1.5 bg-white/[0.015] border-b border-white/5 cursor-pointer hover:bg-white/[0.03] transition-colors focus:outline-none focus:ring-1 focus:ring-purple-500/30"
            onClick={() => toggleCollapse(parent.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleCollapse(parent.id);
              }
            }}
          >
            <span className="text-[10px] text-gray-600 select-none">{isCollapsed ? "▶" : "▼"}</span>
            <span className="text-[11px] font-semibold text-gray-500 pl-2">
              {parent.title} — {children.length} sub-project{children.length !== 1 ? "s" : ""}
            </span>
          </div>,
        );

        if (!isCollapsed) {
          for (const child of children) {
            rows.push(
              <div key={child.id} className="pl-4">
                {renderRow(child)}
              </div>,
            );
          }
        }
      }
    }

    // Orphaned children (parent not in visible list)
    for (const p of projects) {
      if (p.parent_project_id && !roots.find((r) => r.id === p.parent_project_id)) {
        rows.push(renderRow(p));
      }
    }

    return rows;
  };

  return (
    <div className="flex flex-col w-full">
      {/* Sticky header */}
      <div className={`sticky top-0 z-10 bg-[rgba(13,13,26,0.95)] backdrop-blur-sm ${HEADER_BASE}`}>
        {/* Status */}
        <div className="w-12 flex-shrink-0" />

        {/* Project */}
        <button
          type="button"
          className="flex-1 min-w-0 text-left flex items-center"
          onClick={() => toggleSort("project")}
          aria-sort={sort.column === "project" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        >
          Project
          <SortIndicator column="project" sort={sort} />
        </button>

        {/* System */}
        <button
          type="button"
          className="w-36 flex-shrink-0 text-left flex items-center"
          onClick={() => toggleSort("system")}
          aria-sort={sort.column === "system" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        >
          System
          <SortIndicator column="system" sort={sort} />
        </button>

        {/* Todo */}
        <button
          type="button"
          className="w-16 flex-shrink-0 text-center flex items-center justify-center"
          onClick={() => toggleSort("todo")}
          aria-sort={sort.column === "todo" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        >
          Todo
          <SortIndicator column="todo" sort={sort} />
        </button>

        {/* Doing */}
        <button
          type="button"
          className="w-16 flex-shrink-0 text-center flex items-center justify-center"
          onClick={() => toggleSort("doing")}
          aria-sort={sort.column === "doing" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        >
          Doing
          <SortIndicator column="doing" sort={sort} />
        </button>

        {/* Done */}
        <button
          type="button"
          className="w-16 flex-shrink-0 text-center flex items-center justify-center"
          onClick={() => toggleSort("done")}
          aria-sort={sort.column === "done" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        >
          Done
          <SortIndicator column="done" sort={sort} />
        </button>

        {/* Tags */}
        <div className="w-32 flex-shrink-0">Tags</div>

        {/* Activity */}
        <button
          type="button"
          className="w-28 flex-shrink-0 text-right flex items-center justify-end"
          onClick={() => toggleSort("activity")}
          aria-sort={sort.column === "activity" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        >
          Activity
          <SortIndicator column="activity" sort={sort} />
        </button>
      </div>

      {/* Rows */}
      <div>{groupByParent ? renderGrouped() : projects.map(renderRow)}</div>
    </div>
  );
}
