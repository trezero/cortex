/**
 * Knowledge Tab for Project View
 * Shows knowledge sources associated with a project via metadata.project_id
 * Split layout: source list (left) + inline inspector (right)
 */
import { BookOpen, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { cn } from "@/features/ui/primitives/styles";
import type { KnowledgeItem } from "./types";
import { useProjectKnowledgeSources } from "./hooks/useProjectKnowledgeQueries";
import { ProjectSourceCard } from "./components/ProjectSourceCard";
import { ProjectSourceInspector } from "./components/ProjectSourceInspector";

interface KnowledgeTabProps {
	projectId: string;
}

export function KnowledgeTab({ projectId }: KnowledgeTabProps) {
	const { data, isLoading, error } = useProjectKnowledgeSources(projectId);
	const [selectedSource, setSelectedSource] = useState<KnowledgeItem | null>(null);
	const [searchQuery, setSearchQuery] = useState("");

	const sources = data?.items || [];

	// Filter sources by search query
	const filteredSources = useMemo(() => {
		if (!searchQuery) return sources;
		const q = searchQuery.toLowerCase();
		return sources.filter((s) => s.title.toLowerCase().includes(q));
	}, [sources, searchQuery]);

	// Auto-select first source when data loads
	useEffect(() => {
		if (!selectedSource && filteredSources.length > 0) {
			setSelectedSource(filteredSources[0]);
		}
	}, [filteredSources, selectedSource]);

	// Sync selection when sources change
	useEffect(() => {
		if (selectedSource && !sources.find((s) => s.source_id === selectedSource.source_id)) {
			setSelectedSource(sources.length > 0 ? sources[0] : null);
		}
	}, [sources, selectedSource]);

	if (isLoading) {
		return (
			<div className="h-[600px] flex items-center justify-center text-gray-500">
				<div className="animate-pulse">Loading knowledge sources...</div>
			</div>
		);
	}

	if (error) {
		return (
			<div className="h-[600px] flex items-center justify-center text-red-400">
				Failed to load knowledge sources
			</div>
		);
	}

	if (sources.length === 0) {
		return (
			<div className="h-[600px] flex flex-col items-center justify-center text-gray-500 gap-3">
				<BookOpen className="w-12 h-12 text-gray-600" aria-hidden="true" />
				<p className="text-sm">No knowledge sources linked to this project</p>
				<p className="text-xs text-gray-600">Use MCP tools to ingest documentation with this project's ID</p>
			</div>
		);
	}

	return (
		<div className="h-[600px] flex border border-white/10 rounded-lg overflow-hidden bg-black/20">
			{/* Left: Source list */}
			<div className="w-64 shrink-0 border-r border-white/10 flex flex-col">
				{/* Search */}
				<div className="p-2 border-b border-white/10">
					<div className="relative">
						<Search
							className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500"
							aria-hidden="true"
						/>
						<input
							type="text"
							placeholder="Filter sources..."
							value={searchQuery}
							onChange={(e) => setSearchQuery(e.target.value)}
							className={cn(
								"w-full pl-7 pr-2 py-1.5 text-xs bg-white/5 border border-white/10 rounded",
								"text-gray-300 placeholder:text-gray-600",
								"focus:outline-none focus:border-cyan-500/50",
							)}
						/>
					</div>
				</div>

				{/* Source list */}
				<div className="flex-1 overflow-y-auto">
					{filteredSources.map((source) => (
						<ProjectSourceCard
							key={source.source_id}
							source={source}
							isSelected={selectedSource?.source_id === source.source_id}
							onSelect={setSelectedSource}
						/>
					))}
					{filteredSources.length === 0 && searchQuery && (
						<div className="p-4 text-xs text-gray-600 text-center">No matching sources</div>
					)}
				</div>

				{/* Count footer */}
				<div className="px-3 py-2 border-t border-white/10 text-xs text-gray-500">
					{filteredSources.length} source{filteredSources.length !== 1 ? "s" : ""}
				</div>
			</div>

			{/* Right: Inspector */}
			<div className="flex-1 min-w-0 flex flex-col">
				{selectedSource ? (
					<ProjectSourceInspector source={selectedSource} />
				) : (
					<div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
						Select a source to inspect
					</div>
				)}
			</div>
		</div>
	);
}
