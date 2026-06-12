/**
 * ProfileSettings - User profile section for the Settings page.
 *
 * Allows the user to configure display name, bio, long-term goals,
 * and current priorities. Data is persisted via the chat profile API.
 */

import { useState, useEffect } from "react";
import { Plus, X, Save, Loader } from "lucide-react";
import { useProfile, useUpdateProfile } from "../../features/chat/hooks/useChatQueries";
import { useToast } from "../../features/shared/hooks/useToast";

export function ProfileSettings() {
  const { data: profile, isLoading: profileLoading } = useProfile();
  const updateProfile = useUpdateProfile();
  const { showToast } = useToast();

  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [goals, setGoals] = useState<string[]>([]);
  const [priorities, setPriorities] = useState<string[]>([]);
  const [newGoal, setNewGoal] = useState("");
  const [newPriority, setNewPriority] = useState("");

  // Sync local state when profile loads
  useEffect(() => {
    if (profile) {
      setDisplayName(profile.display_name ?? "");
      setBio(profile.bio ?? "");
      setGoals(profile.long_term_goals ?? []);
      setPriorities(profile.current_priorities ?? []);
    }
  }, [profile]);

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

  const handleAddPriority = () => {
    const trimmed = newPriority.trim();
    if (trimmed && !priorities.includes(trimmed)) {
      setPriorities([...priorities, trimmed]);
      setNewPriority("");
    }
  };

  const handleRemovePriority = (index: number) => {
    setPriorities(priorities.filter((_, i) => i !== index));
  };

  const handleSave = () => {
    updateProfile.mutate(
      {
        display_name: displayName || null,
        bio: bio || null,
        long_term_goals: goals,
        current_priorities: priorities,
      } as Partial<typeof profile> & Record<string, unknown>,
      {
        onSuccess: () => showToast("Profile saved", "success"),
        onError: () => showToast("Failed to save profile", "error"),
      },
    );
  };

  if (profileLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader className="animate-spin text-gray-500" size={20} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Display name */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Display Name
        </label>
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="How should Cortex address you?"
          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 focus:border-cyan-500/50 focus:outline-none"
        />
      </div>

      {/* Bio */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Bio
        </label>
        <textarea
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          placeholder="Tell Cortex about your background and expertise..."
          rows={3}
          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 focus:border-cyan-500/50 focus:outline-none resize-none"
        />
      </div>

      {/* Long-term goals */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Long-term Goals
        </label>
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

      {/* Current priorities */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Current Priorities
        </label>
        <div className="space-y-2 mb-2">
          {priorities.map((priority, i) => (
            <div key={i} className="flex items-center gap-2 group">
              <span className="flex-1 text-sm text-gray-300 bg-white/5 border border-white/10 rounded-md px-3 py-1.5">
                {priority}
              </span>
              <button
                type="button"
                onClick={() => handleRemovePriority(i)}
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
            value={newPriority}
            onChange={(e) => setNewPriority(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddPriority()}
            placeholder="Add a priority..."
            className="flex-1 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 focus:border-cyan-500/50 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAddPriority}
            disabled={!newPriority.trim()}
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
          disabled={updateProfile.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-sm font-medium hover:bg-cyan-500/25 disabled:opacity-50 transition-colors"
        >
          {updateProfile.isPending ? (
            <Loader className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          Save Profile
        </button>
      </div>
    </div>
  );
}
