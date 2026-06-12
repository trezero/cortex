/**
 * Inline inspector for a knowledge source within the project knowledge tab.
 * Reuses knowledge inspector internals but renders inline instead of in a dialog.
 */
import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { copyToClipboard } from "@/features/shared/utils/clipboard";
import { ContentViewer } from "@/features/knowledge/inspector/components/ContentViewer";
import { InspectorHeader } from "@/features/knowledge/inspector/components/InspectorHeader";
import { InspectorSidebar } from "@/features/knowledge/inspector/components/InspectorSidebar";
import { useInspectorPagination } from "@/features/knowledge/inspector/hooks/useInspectorPagination";
import type { CodeExample, DocumentChunk, InspectorSelectedItem, KnowledgeItem } from "../types";

interface ProjectSourceInspectorProps {
	source: KnowledgeItem;
}

type ViewMode = "documents" | "code";

export function ProjectSourceInspector({ source }: ProjectSourceInspectorProps) {
	const navigate = useNavigate();
	const [viewMode, setViewMode] = useState<ViewMode>("documents");
	const [searchQuery, setSearchQuery] = useState("");
	const [selectedItem, setSelectedItem] = useState<InspectorSelectedItem | null>(null);
	const [copiedId, setCopiedId] = useState<string | null>(null);

	// Reset when source changes
	useEffect(() => {
		setViewMode("documents");
		setSelectedItem(null);
		setSearchQuery("");
	}, [source.source_id]);

	// Reuse the existing pagination hook from knowledge inspector
	const paginationData = useInspectorPagination({
		sourceId: source.source_id,
		viewMode,
		searchQuery,
	});

	const currentItems = paginationData.items;
	const totalDocumentCount = source.document_count ?? source.metadata?.document_count ?? 0;
	const totalCodeCount = source.code_examples_count ?? source.metadata?.code_examples_count ?? 0;

	// Auto-select first item when data loads
	useEffect(() => {
		if (selectedItem || currentItems.length === 0) return;

		const firstItem = currentItems[0];
		if (viewMode === "documents") {
			const firstDoc = firstItem as DocumentChunk;
			setSelectedItem({
				type: "document",
				id: firstDoc.id,
				content: firstDoc.content || "",
				metadata: {
					title: firstDoc.title || firstDoc.metadata?.title,
					section: firstDoc.section || firstDoc.metadata?.section,
					relevance_score: firstDoc.metadata?.relevance_score,
					url: firstDoc.url || firstDoc.metadata?.url,
					tags: firstDoc.metadata?.tags,
				},
			});
		} else {
			const firstCode = firstItem as CodeExample;
			setSelectedItem({
				type: "code",
				id: String(firstCode.id || ""),
				content: firstCode.content || firstCode.code || "",
				metadata: {
					language: firstCode.language,
					file_path: firstCode.file_path,
					summary: firstCode.summary,
					relevance_score: firstCode.metadata?.relevance_score,
				},
			});
		}
	}, [viewMode, currentItems, selectedItem]);

	const handleCopy = useCallback(async (text: string, id: string) => {
		const result = await copyToClipboard(text);
		if (result.success) {
			setCopiedId(id);
			setTimeout(() => setCopiedId((v) => (v === id ? null : v)), 2000);
		}
	}, []);

	const handleItemSelect = useCallback(
		(item: DocumentChunk | CodeExample) => {
			if (viewMode === "documents") {
				const doc = item as DocumentChunk;
				setSelectedItem({
					type: "document",
					id: doc.id || "",
					content: doc.content || "",
					metadata: {
						title: doc.title || doc.metadata?.title,
						section: doc.section || doc.metadata?.section,
						relevance_score: doc.metadata?.relevance_score,
						url: doc.url || doc.metadata?.url,
						tags: doc.metadata?.tags,
					},
				});
			} else {
				const code = item as CodeExample;
				setSelectedItem({
					type: "code",
					id: String(code.id),
					content: code.content || code.code || "",
					metadata: {
						language: code.language,
						file_path: code.file_path,
						summary: code.summary,
						relevance_score: code.metadata?.relevance_score,
					},
				});
			}
		},
		[viewMode],
	);

	const handleViewModeChange = useCallback((mode: ViewMode) => {
		setViewMode(mode);
		setSelectedItem(null);
		setSearchQuery("");
	}, []);

	return (
		<div className="flex flex-col h-full">
			{/* Source header with link to Knowledge page */}
			<div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
				<h3 className="text-sm font-medium text-white/90 truncate">{source.title}</h3>
				<button
					type="button"
					onClick={() => navigate("/knowledge")}
					className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
					aria-label="View in Knowledge Base"
				>
					<ExternalLink className="w-3 h-3" aria-hidden="true" />
					Knowledge Base
				</button>
			</div>

			{/* Inspector header with view mode toggle */}
			<div className="flex-shrink-0">
				<InspectorHeader
					item={source}
					viewMode={viewMode}
					onViewModeChange={handleViewModeChange}
					documentCount={totalDocumentCount}
					codeCount={totalCodeCount}
					filteredDocumentCount={viewMode === "documents" ? currentItems.length : 0}
					filteredCodeCount={viewMode === "code" ? currentItems.length : 0}
				/>
			</div>

			{/* Split view: sidebar + content */}
			<div className="flex flex-1 min-h-0">
				<InspectorSidebar
					viewMode={viewMode}
					searchQuery={searchQuery}
					onSearchChange={setSearchQuery}
					items={currentItems as DocumentChunk[] | CodeExample[]}
					selectedItemId={selectedItem?.id || null}
					onItemSelect={handleItemSelect}
					isLoading={paginationData.isLoading}
					hasNextPage={paginationData.hasNextPage}
					onLoadMore={paginationData.fetchNextPage}
					isFetchingNextPage={paginationData.isFetchingNextPage}
				/>
				<div className="flex-1 min-h-0 min-w-0 bg-black/20 flex flex-col">
					<ContentViewer selectedItem={selectedItem} onCopy={handleCopy} copiedId={copiedId} />
				</div>
			</div>
		</div>
	);
}
