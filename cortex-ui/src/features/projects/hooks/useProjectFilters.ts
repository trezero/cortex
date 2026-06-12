import { useCallback, useDeferredValue, useState } from "react";
import type { Project } from "../types";

export type ViewMode = "grid" | "table";
export type SortColumn = "project" | "system" | "todo" | "doing" | "done" | "activity";
export type SortDirection = "asc" | "desc";

export interface SortState {
  column: SortColumn;
  direction: SortDirection;
}

const STORAGE_KEYS = {
  activeFilter: "cortex_projects_active_filter",
  viewMode: "cortex_projects_view_mode",
  sort: "cortex_projects_sort",
} as const;

function loadFromStorage<T>(key: string, fallback: T): T {
  try {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : fallback;
  } catch {
    return fallback;
  }
}

function saveToStorage(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage unavailable — ignore
  }
}

export function useProjectFilters() {
  // Persisted state
  const [activeOnly, setActiveOnlyRaw] = useState(() =>
    loadFromStorage(STORAGE_KEYS.activeFilter, false),
  );
  const [viewMode, setViewModeRaw] = useState<ViewMode>(() =>
    loadFromStorage(STORAGE_KEYS.viewMode, "grid"),
  );
  const [sort, setSortRaw] = useState<SortState>(() =>
    loadFromStorage(STORAGE_KEYS.sort, { column: "activity" as SortColumn, direction: "desc" as SortDirection }),
  );

  // Non-persisted state
  const [systemId, setSystemId] = useState<string>("");
  const [tag, setTag] = useState<string>("");
  const [groupByParent, setGroupByParent] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearch = useDeferredValue(searchQuery);

  // Persisted setters
  const setActiveOnly = useCallback((value: boolean) => {
    setActiveOnlyRaw(value);
    saveToStorage(STORAGE_KEYS.activeFilter, value);
  }, []);

  const setViewMode = useCallback((value: ViewMode) => {
    setViewModeRaw(value);
    saveToStorage(STORAGE_KEYS.viewMode, value);
  }, []);

  const setSort = useCallback((value: SortState | ((prev: SortState) => SortState)) => {
    setSortRaw((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      saveToStorage(STORAGE_KEYS.sort, next);
      return next;
    });
  }, []);

  const toggleSort = useCallback((column: SortColumn) => {
    setSort((prev) => ({
      column,
      direction: prev.column === column && prev.direction === "asc" ? "desc" : "asc",
    }));
  }, [setSort]);

  // Filter function
  const filterProjects = useCallback(
    (projects: Project[]): Project[] => {
      let filtered = projects;

      if (activeOnly) {
        filtered = filtered.filter((p) => p.pinned);
      }
      if (systemId) {
        filtered = filtered.filter((p) =>
          p.system_registrations?.some((r) => r.system_id === systemId),
        );
      }
      if (tag) {
        filtered = filtered.filter((p) => p.tags?.includes(tag));
      }
      if (deferredSearch) {
        const q = deferredSearch.toLowerCase();
        filtered = filtered.filter((p) => p.title.toLowerCase().includes(q));
      }

      return filtered;
    },
    [activeOnly, systemId, tag, deferredSearch],
  );

  // Sort function
  const sortProjects = useCallback(
    (projects: Project[], mode: ViewMode): Project[] => {
      const sorted = [...projects];
      const pinnedFirst = (a: Project, b: Project) =>
        (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);

      if (mode === "grid") {
        // Fixed: pinned first, then by updated_at descending
        return sorted.sort((a, b) => {
          const pin = pinnedFirst(a, b);
          if (pin !== 0) return pin;
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });
      }

      // Table: pinned first, then by user-selected column
      return sorted.sort((a, b) => {
        const pin = pinnedFirst(a, b);
        if (pin !== 0) return pin;

        const dir = sort.direction === "asc" ? 1 : -1;
        switch (sort.column) {
          case "project":
            return dir * a.title.localeCompare(b.title);
          case "system": {
            const aName = a.system_registrations?.[0]?.system_name ?? "";
            const bName = b.system_registrations?.[0]?.system_name ?? "";
            return dir * aName.localeCompare(bName);
          }
          case "activity":
            return dir * (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime());
          default:
            return 0;
        }
      });
    },
    [sort],
  );

  // Extract unique tags from all projects
  const extractTags = useCallback((projects: Project[]): string[] => {
    const tagSet = new Set<string>();
    for (const p of projects) {
      for (const t of p.tags ?? []) {
        tagSet.add(t);
      }
    }
    return Array.from(tagSet).sort();
  }, []);

  return {
    // Filter state
    activeOnly,
    setActiveOnly,
    systemId,
    setSystemId,
    tag,
    setTag,
    groupByParent,
    setGroupByParent,
    searchQuery,
    setSearchQuery,
    // View state
    viewMode,
    setViewMode,
    sort,
    setSort,
    toggleSort,
    // Utilities
    filterProjects,
    sortProjects,
    extractTags,
  };
}
