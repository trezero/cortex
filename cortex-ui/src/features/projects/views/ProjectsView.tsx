import { FileText, Library, ListTodo, Puzzle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { DeleteConfirmModal } from "../../ui/components/DeleteConfirmModal";
import { PillNavigation } from "../../ui/primitives";
import { ManageSubProjectsModal } from "../components/ManageSubProjectsModal";
import { NewProjectModal } from "../components/NewProjectModal";
import { ProjectFilterBar } from "../components/ProjectFilterBar";
import { ProjectGrid } from "../components/ProjectGrid";
import { ProjectTable } from "../components/ProjectTable";
import { SubProjectsStrip } from "../components/SubProjectsStrip";
import { DocsTab } from "../documents/DocsTab";
import { ExtensionsTab } from "../extensions/ExtensionsTab";
import { useProjectFilters } from "../hooks/useProjectFilters";
import { useDeleteProject, useProjects, useUpdateProject } from "../hooks/useProjectQueries";
import { useSystems } from "../hooks/useSystemQueries";
import { KnowledgeTab } from "../knowledge/KnowledgeTab";
import { useTaskCounts } from "../tasks/hooks";
import { TasksTab } from "../tasks/TasksTab";
import type { Project } from "../types";

interface ProjectsViewProps {
	className?: string;
	"data-id"?: string;
}

export function ProjectsView({ className = "", "data-id": dataId }: ProjectsViewProps) {
	const { projectId } = useParams();
	const navigate = useNavigate();

	// State
	const [selectedProject, setSelectedProject] = useState<Project | null>(null);
	const [activeTab, setActiveTab] = useState("tasks");
	const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
	const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
	const [projectToDelete, setProjectToDelete] = useState<{ id: string; title: string } | null>(null);
	const [isManageSubProjectsOpen, setIsManageSubProjectsOpen] = useState(false);

	// Hooks
	const filters = useProjectFilters();
	const { data: systems = [] } = useSystems();
	const { data: projects = [], isLoading, error } = useProjects();
	const { data: taskCounts = {}, refetch: refetchTaskCounts } = useTaskCounts();
	const deleteProjectMutation = useDeleteProject();
	const updateProjectMutation = useUpdateProject();

	const handleTogglePin = useCallback(
		(id: string, pinned: boolean) => {
			updateProjectMutation.mutate({ projectId: id, updates: { pinned } });
		},
		[updateProjectMutation],
	);

	// Apply filters and sort
	const filteredProjects = filters.filterProjects(projects as Project[]);
	const sortedProjects = filters.sortProjects(filteredProjects, filters.viewMode);
	const availableTags = filters.extractTags(projects as Project[]);

	// Derived parent/child info for the selected project
	const selectedIsParent = selectedProject
		? (projects as Project[]).some((p) => p.parent_project_id === selectedProject.id)
		: false;

	const selectedIsChild = !!selectedProject?.parent_project_id;

	const selectedParentTitle = selectedProject?.parent_project_id
		? (projects as Project[]).find((p) => p.id === selectedProject.parent_project_id)?.title
		: undefined;

	// The strip parent ID: either the selected project (if it's a parent) or its parent (if it's a child)
	const stripParentId = selectedIsParent
		? selectedProject?.id
		: selectedIsChild
			? selectedProject?.parent_project_id
			: undefined;

	// Handle project selection by ID
	const handleProjectSelect = useCallback(
		(id: string) => {
			const project = (projects as Project[]).find((p) => p.id === id);
			if (!project || selectedProject?.id === id) return;
			setSelectedProject(project);
			setActiveTab("tasks");
			navigate(`/projects/${id}`, { replace: true });
		},
		[projects, selectedProject?.id, navigate],
	);

	// Auto-select project based on URL or default to first
	useEffect(() => {
		if (!(projects as Project[]).length) return;

		if (projectId) {
			const project = (projects as Project[]).find((p) => p.id === projectId);
			if (project) {
				setSelectedProject(project);
				return;
			}
		}

		if (!selectedProject || !(projects as Project[]).find((p) => p.id === selectedProject.id)) {
			const first = (projects as Project[])[0];
			setSelectedProject(first);
			navigate(`/projects/${first.id}`, { replace: true });
		}
	}, [projects, projectId, selectedProject, navigate]);

	// Refetch task counts when projects change
	useEffect(() => {
		if ((projects as Project[]).length > 0) {
			refetchTaskCounts();
		}
	}, [projects, refetchTaskCounts]);

	const confirmDeleteProject = () => {
		if (!projectToDelete) return;

		deleteProjectMutation.mutate(projectToDelete.id, {
			onSuccess: () => {
				setShowDeleteConfirm(false);
				setProjectToDelete(null);

				// If we deleted the selected project, select another one
				if (selectedProject?.id === projectToDelete.id) {
					const remainingProjects = (projects as Project[]).filter((p) => p.id !== projectToDelete.id);
					if (remainingProjects.length > 0) {
						const nextProject = remainingProjects[0];
						setSelectedProject(nextProject);
						navigate(`/projects/${nextProject.id}`, { replace: true });
					} else {
						setSelectedProject(null);
						navigate("/projects", { replace: true });
					}
				}
			},
		});
	};

	const cancelDeleteProject = () => {
		setShowDeleteConfirm(false);
		setProjectToDelete(null);
	};

	return (
		<div className={`flex flex-col h-full ${className}`} data-id={dataId}>
			{/* Filter Bar */}
			<ProjectFilterBar
				activeOnly={filters.activeOnly}
				setActiveOnly={filters.setActiveOnly}
				systemId={filters.systemId}
				setSystemId={filters.setSystemId}
				tag={filters.tag}
				setTag={filters.setTag}
				groupByParent={filters.groupByParent}
				setGroupByParent={filters.setGroupByParent}
				searchQuery={filters.searchQuery}
				setSearchQuery={filters.setSearchQuery}
				viewMode={filters.viewMode}
				setViewMode={filters.setViewMode}
				systems={systems}
				tags={availableTags}
				totalCount={(projects as Project[]).length}
				filteredCount={sortedProjects.length}
				onNewProject={() => setIsNewProjectModalOpen(true)}
			/>

			{/* Loading state */}
			{isLoading && (
				<div className="flex items-center justify-center py-16 text-gray-500 text-sm">Loading projects...</div>
			)}

			{/* Error state */}
			{error && (
				<div className="flex items-center justify-center py-16 text-red-400 text-sm">
					Failed to load projects
				</div>
			)}

			{/* Grid/Table area */}
			{!isLoading && !error && (
				<div className={selectedProject ? "max-h-[340px] overflow-y-auto" : "flex-1 overflow-y-auto"}>
					{/* Active filter empty state */}
					{filters.activeOnly && sortedProjects.length === 0 && (projects as Project[]).length > 0 ? (
						<div className="flex items-center justify-center py-16 text-gray-500 text-sm">
							No active projects. Pin projects to see them here.
						</div>
					) : filters.viewMode === "grid" ? (
						<ProjectGrid
							projects={sortedProjects}
							allProjects={projects as Project[]}
							taskCounts={taskCounts}
							selectedProjectId={selectedProject?.id}
							onSelectProject={handleProjectSelect}
							onTogglePin={handleTogglePin}
							groupByParent={filters.groupByParent}
						/>
					) : (
						<ProjectTable
							projects={sortedProjects}
							allProjects={projects as Project[]}
							taskCounts={taskCounts}
							selectedProjectId={selectedProject?.id}
							onSelectProject={handleProjectSelect}
							onTogglePin={handleTogglePin}
							sort={filters.sort}
							toggleSort={filters.toggleSort}
							groupByParent={filters.groupByParent}
						/>
					)}
				</div>
			)}

			{/* Sub-projects strip — visible when a parent or any of its children is selected */}
			{selectedProject && stripParentId && (
				<SubProjectsStrip
					parentProjectId={stripParentId}
					selectedProjectId={selectedProject.id}
					onSelectProject={handleProjectSelect}
					onManage={() => setIsManageSubProjectsOpen(true)}
				/>
			)}

			{/* Project detail tabs */}
			{selectedProject && (
				<div className="flex-1 min-h-0 overflow-y-auto mt-4">
					{/* Breadcrumb for child projects */}
					{selectedParentTitle && selectedProject?.parent_project_id && (
						<div className="flex items-center gap-1.5 text-sm text-gray-500 mb-2 px-1">
							<button
								type="button"
								className="hover:text-cyan-400 transition-colors truncate max-w-[200px]"
								onClick={() => {
									if (selectedProject.parent_project_id) {
										handleProjectSelect(selectedProject.parent_project_id);
									}
								}}
							>
								{selectedParentTitle}
							</button>
							<span className="text-gray-600">&rsaquo;</span>
							<span className="text-gray-400 truncate">{selectedProject.title}</span>
						</div>
					)}
					<div className="flex items-center justify-between mb-6">
						<div className="flex-1" />
						<PillNavigation
							items={[
								{ id: "docs", label: "Docs", icon: <FileText className="w-4 h-4" /> },
								{ id: "knowledge", label: "Knowledge", icon: <Library className="w-4 h-4" /> },
								{ id: "extensions", label: "Extensions", icon: <Puzzle className="w-4 h-4" /> },
								{ id: "tasks", label: "Tasks", icon: <ListTodo className="w-4 h-4" /> },
							]}
							activeSection={activeTab}
							onSectionClick={(id) => setActiveTab(id as string)}
							colorVariant="orange"
							size="small"
							showIcons={true}
							showText={true}
							hasSubmenus={false}
						/>
						<div className="flex-1" />
					</div>
					<div>
						{activeTab === "docs" && <DocsTab project={selectedProject} />}
						{activeTab === "knowledge" && <KnowledgeTab projectId={selectedProject.id} />}
						{activeTab === "extensions" && <ExtensionsTab projectId={selectedProject.id} />}
						{activeTab === "tasks" && <TasksTab projectId={selectedProject.id} />}
					</div>
				</div>
			)}

			{/* Modals */}
			<NewProjectModal
				open={isNewProjectModalOpen}
				onOpenChange={setIsNewProjectModalOpen}
				onSuccess={() => refetchTaskCounts()}
			/>

			{showDeleteConfirm && projectToDelete && (
				<DeleteConfirmModal
					itemName={projectToDelete.title}
					onConfirm={confirmDeleteProject}
					onCancel={cancelDeleteProject}
					type="project"
					open={showDeleteConfirm}
					onOpenChange={setShowDeleteConfirm}
				/>
			)}

			{selectedProject && (
				<ManageSubProjectsModal
					parentProjectId={selectedProject.id}
					parentTitle={selectedProject.title}
					open={isManageSubProjectsOpen}
					onOpenChange={setIsManageSubProjectsOpen}
				/>
			)}
		</div>
	);
}
