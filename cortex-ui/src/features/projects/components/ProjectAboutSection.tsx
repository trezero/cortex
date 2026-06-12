/**
 * ProjectAboutSection - Editable "About" panel for project enrichment fields.
 *
 * Displays and allows editing of project_goals, project_relevance, and
 * project_category. Used on the project detail view to give the AI
 * context for prioritization and synergy analysis.
 */

import { useState, useEffect } from "react";
import { Plus, X, Save, Loader } from "lucide-react";
import { useUpdateProject } from "../hooks/useProjectQueries";
import { useToast } from "../../shared/hooks/useToast";
import type { Project } from "../types";

interface ProjectAboutSectionProps {
  project: Project;
}

export function ProjectAboutSection({ project }: ProjectAboutSectionProps) {
  const updateProject = useUpdateProject();
  const { showToast } = useToast();

  const [goals, setGoals] = useState<string[]>([]);
  const [newGoal, setNewGoal] = useState("");
  const [relevance, setRelevance] = useState("");
  const [category, setCategory] = useState("");

  // Sync local state when project data changes
  useEffect(() => {
    setGoals(project.project_goals ?? []);
    setRelevance(project.project_relevance ?? "");
    setCategory(project.project_category ?? "");
  }, [project.id, project.project_goals, project.project_relevance, project.project_category]);

  const handleAddGoal = () => {
    const trimmed = newGoal.trim();
    if (trimmed && !goals.includes(trimmed)) {
      setGoals([...goals, trimmed]);
      setNewGoal("");
    }
  };

  const handleRemoveGoal = (index: number) => {
    setGoals(goals.filter((_, i) => i !== index));
  };

  const handleSave = () => {
    updateProject.mutate(
      {
        projectId: project.id,
        updates: {
          project_goals: goals,
          project_relevance: relevance || undefined,
          project_category: category || undefined,
        },
      },
      {
        onSuccess: () => showToast("Project details saved", "success"),
        onError: () => showToast("Failed to save project details", "error"),
      },
    );
  };

  return (
    <div className="rounded-xl border border-white/10 backdrop-blur-xl bg-white/5 p-5 space-y-5">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">About</h3>

      {/* Project Category */}
      <div>
        <label className="block text-sm font-medium text-gray-400 mb-1">Category</label>
        <input
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="e.g. Web App, CLI Tool, Library, Infrastructure..."
          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 focus:border-cyan-500/50 focus:outline-none"
        />
      </div>

      {/* Project Relevance */}
      <div>
        <label className="block text-sm font-medium text-gray-400 mb-1">Relevance</label>
        <textarea
          value={relevance}
          onChange={(e) => setRelevance(e.target.value)}
          placeholder="How does this project relate to your overall objectives?"
          rows={3}
          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 focus:border-cyan-500/50 focus:outline-none resize-none"
        />
      </div>

      {/* Project Goals */}
      <div>
        <label className="block text-sm font-medium text-gray-400 mb-1">Goals</label>
        <div className="space-y-2 mb-2">
          {goals.map((goal, i) => (
            <div key={i} className="flex items-center gap-2 group">
              <span className="flex-1 text-sm text-gray-300 bg-white/5 border border-white/10 rounded-md px-3 py-1.5">
                {goal}
              </span>
              <button
                type="button"
                onClick={() => handleRemoveGoal(i)}
                className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newGoal}
            onChange={(e) => setNewGoal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddGoal()}
            placeholder="Add a goal..."
            className="flex-1 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 focus:border-cyan-500/50 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAddGoal}
            disabled={!newGoal.trim()}
            className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Save button */}
      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={updateProject.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-sm font-medium hover:bg-cyan-500/25 disabled:opacity-50 transition-colors"
        >
          {updateProject.isPending ? (
            <Loader className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          Save
        </button>
      </div>
    </div>
  );
}
