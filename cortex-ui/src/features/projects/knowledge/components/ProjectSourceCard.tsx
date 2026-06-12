/**
 * Compact card for a knowledge source within the project knowledge tab.
 * Shows title, type, counts, and status.
 */
import { FileText, Code2, Globe, FileUp } from "lucide-react";
import { cn } from "@/features/ui/primitives/styles";
import type { KnowledgeItem } from "../types";

interface ProjectSourceCardProps {
	source: KnowledgeItem;
	isSelected: boolean;
	onSelect: (source: KnowledgeItem) => void;
}

export function ProjectSourceCard({ source, isSelected, onSelect }: ProjectSourceCardProps) {
	const isUrl = source.source_type === "url";
	const SourceIcon = isUrl ? Globe : FileUp;

	return (
		<div
			role="button"
			tabIndex={0}
			onClick={() => onSelect(source)}
			onKeyDown={(e) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					onSelect(source);
				}
			}}
			aria-selected={isSelected}
			className={cn(
				"group px-3 py-2.5 cursor-pointer border-b border-white/5",
				"transition-all duration-150",
				isSelected
					? "bg-cyan-500/10 border-l-2 border-l-cyan-400"
					: "hover:bg-white/5 border-l-2 border-l-transparent",
			)}
		>
			{/* Title row */}
			<div className="flex items-center gap-2 mb-1">
				<SourceIcon
					className={cn("w-3.5 h-3.5 shrink-0", isSelected ? "text-cyan-400" : "text-gray-500")}
					aria-hidden="true"
				/>
				<span className={cn("text-sm font-medium truncate", isSelected ? "text-cyan-100" : "text-gray-300")}>
					{source.title}
				</span>
			</div>

			{/* Stats row */}
			<div className="flex items-center gap-3 ml-5.5 text-xs text-gray-500">
				<span className="flex items-center gap-1">
					<FileText className="w-3 h-3" aria-hidden="true" />
					{source.document_count}
				</span>
				{source.code_examples_count > 0 && (
					<span className="flex items-center gap-1">
						<Code2 className="w-3 h-3" aria-hidden="true" />
						{source.code_examples_count}
					</span>
				)}
				<span
					className={cn(
						"capitalize text-[10px] px-1.5 py-0.5 rounded-full",
						source.knowledge_type === "technical"
							? "bg-cyan-500/10 text-cyan-400"
							: "bg-purple-500/10 text-purple-400",
					)}
				>
					{source.knowledge_type}
				</span>
			</div>
		</div>
	);
}
