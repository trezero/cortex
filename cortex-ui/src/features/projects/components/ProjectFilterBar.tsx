import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../ui/primitives/select";
import type { SystemSummary } from "../services/systemService";
import type { ViewMode } from "../hooks/useProjectFilters";

interface ProjectFilterBarProps {
  // Filter state
  activeOnly: boolean;
  setActiveOnly: (value: boolean) => void;
  systemId: string;
  setSystemId: (value: string) => void;
  tag: string;
  setTag: (value: string) => void;
  groupByParent: boolean;
  setGroupByParent: (value: boolean) => void;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  // View state
  viewMode: ViewMode;
  setViewMode: (value: ViewMode) => void;
  // Data
  systems: SystemSummary[];
  tags: string[];
  totalCount: number;
  filteredCount: number;
  // Actions
  onNewProject: () => void;
}

export function ProjectFilterBar({
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
  viewMode,
  setViewMode,
  systems,
  tags,
  totalCount,
  filteredCount,
  onNewProject,
}: ProjectFilterBarProps) {
  const isFiltered = activeOnly || !!systemId || !!tag || !!searchQuery;

  return (
    <div>
      {/* Filter bar */}
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-purple-500/15 bg-[rgba(15,15,30,0.9)] flex-wrap">
        {/* Active toggle */}
        <button
          type="button"
          aria-pressed={activeOnly}
          onClick={() => setActiveOnly(!activeOnly)}
          className={[
            "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all",
            activeOnly
              ? "border border-purple-500/60 bg-gradient-to-br from-purple-600/25 to-indigo-700/15 text-purple-300 shadow-[0_0_12px_rgba(139,92,246,0.3)]"
              : "border border-white/10 bg-white/5 text-gray-500",
          ].join(" ")}
        >
          {activeOnly && (
            <span className="w-2 h-2 rounded-full bg-purple-400 shadow-[0_0_6px_#a78bfa] shrink-0" />
          )}
          Active
        </button>

        {/* Divider */}
        <div className="w-px h-6 bg-purple-500/20" />

        {/* System dropdown */}
        <Select value={systemId || "_all"} onValueChange={(v) => setSystemId(v === "_all" ? "" : v)}>
          <SelectTrigger color="cyan" className="text-sm py-1.5 min-w-[140px]">
            <SelectValue placeholder="All systems" />
          </SelectTrigger>
          <SelectContent color="cyan">
            <SelectItem value="_all" color="cyan">All systems</SelectItem>
            {systems.map((s) => (
              <SelectItem key={s.id} value={s.id} color="cyan">
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Tags dropdown */}
        <Select value={tag || "_all"} onValueChange={(v) => setTag(v === "_all" ? "" : v)}>
          <SelectTrigger color="purple" className="text-sm py-1.5 min-w-[120px]">
            <SelectValue placeholder="All tags" />
          </SelectTrigger>
          <SelectContent color="purple">
            <SelectItem value="_all" color="purple">All tags</SelectItem>
            {tags.map((t) => (
              <SelectItem key={t} value={t} color="purple">
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Group by parent button */}
        <button
          type="button"
          aria-pressed={groupByParent}
          onClick={() => setGroupByParent(!groupByParent)}
          className={[
            "px-3 py-1.5 rounded-lg border text-sm transition-all",
            groupByParent
              ? "border-purple-500/60 bg-gradient-to-br from-purple-600/25 to-indigo-700/15 text-purple-300"
              : "border-white/10 bg-white/5 text-gray-400",
          ].join(" ")}
        >
          Group
        </button>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Search input */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 min-w-[180px]">
          <svg
            className="w-3.5 h-3.5 text-gray-600 shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search projects…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent border-none outline-none text-sm text-gray-300 placeholder-gray-600 w-full"
          />
        </div>

        {/* View toggle */}
        <div className="flex rounded-lg border border-white/10 overflow-hidden">
          <button
            type="button"
            aria-label="Grid view"
            aria-pressed={viewMode === "grid"}
            onClick={() => setViewMode("grid")}
            className={[
              "px-2.5 py-1.5 transition-all",
              viewMode === "grid"
                ? "bg-purple-600/20 text-purple-300"
                : "bg-white/[0.03] text-gray-600",
            ].join(" ")}
          >
            <svg
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 16 16"
              aria-hidden="true"
            >
              <rect x="1" y="1" width="6" height="6" rx="1" />
              <rect x="9" y="1" width="6" height="6" rx="1" />
              <rect x="1" y="9" width="6" height="6" rx="1" />
              <rect x="9" y="9" width="6" height="6" rx="1" />
            </svg>
          </button>
          <button
            type="button"
            aria-label="Table view"
            aria-pressed={viewMode === "table"}
            onClick={() => setViewMode("table")}
            className={[
              "px-2.5 py-1.5 border-l border-white/10 transition-all",
              viewMode === "table"
                ? "bg-purple-600/20 text-purple-300"
                : "bg-white/[0.03] text-gray-600",
            ].join(" ")}
          >
            <svg
              className="w-4 h-4"
              fill="currentColor"
              viewBox="0 0 16 16"
              aria-hidden="true"
            >
              <rect x="1" y="2" width="14" height="2" rx="1" />
              <rect x="1" y="7" width="14" height="2" rx="1" />
              <rect x="1" y="12" width="14" height="2" rx="1" />
            </svg>
          </button>
        </div>

        {/* + New button */}
        <button
          type="button"
          onClick={onNewProject}
          className="px-3.5 py-1.5 rounded-lg border border-purple-500/30 bg-gradient-to-br from-purple-600/15 to-indigo-700/10 text-purple-300 text-sm transition-opacity hover:opacity-90"
        >
          + New
        </button>
      </div>

      {/* Result count */}
      <div className="px-4 py-2 text-xs text-gray-500">
        {isFiltered ? (
          <>
            Showing {filteredCount} filtered{" "}
            <span className="text-gray-600">· {totalCount} total</span>
          </>
        ) : (
          <>Showing {totalCount} projects</>
        )}
      </div>
    </div>
  );
}
