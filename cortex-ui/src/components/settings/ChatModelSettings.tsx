/**
 * ChatModelSettings - Settings section for selecting the default chat model.
 *
 * Persists the user's preferred default model in localStorage. The chat page
 * reads this value as its initial model selection.
 */

import { useState, useEffect } from "react";
import { Save, Loader, Cpu } from "lucide-react";
import { useToast } from "../../features/shared/hooks/useToast";

const STORAGE_KEY = "cortex:chat-default-model";

const AVAILABLE_MODELS = [
  { id: "openai:gpt-4o", label: "GPT-4o" },
  { id: "openai:gpt-4.1", label: "GPT-4.1" },
  { id: "openai:gpt-4.1-mini", label: "GPT-4.1 Mini" },
  { id: "anthropic:claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
  { id: "anthropic:claude-opus-4-20250514", label: "Claude Opus 4" },
  { id: "anthropic:claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
] as const;

export const DEFAULT_CHAT_MODEL = "openai:gpt-4o";

/** Read the persisted default chat model from localStorage. */
export function getDefaultChatModel(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_CHAT_MODEL;
  } catch {
    return DEFAULT_CHAT_MODEL;
  }
}

export function ChatModelSettings() {
  const { showToast } = useToast();
  const [selectedModel, setSelectedModel] = useState(DEFAULT_CHAT_MODEL);
  const [saving, setSaving] = useState(false);

  // Load persisted value on mount
  useEffect(() => {
    setSelectedModel(getDefaultChatModel());
  }, []);

  const handleSave = () => {
    setSaving(true);
    try {
      localStorage.setItem(STORAGE_KEY, selectedModel);
      showToast("Default chat model saved", "success");
    } catch {
      showToast("Failed to save default model", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-400">
        Choose the default AI model for new chat conversations. You can still
        switch models per-conversation from the chat input.
      </p>

      <div>
        <label className="block text-sm font-medium text-gray-400 mb-2">
          Default Model
        </label>
        <div className="relative">
          <Cpu className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 focus:border-cyan-500/50 focus:outline-none appearance-none cursor-pointer"
          >
            {AVAILABLE_MODELS.map((model) => (
              <option key={model.id} value={model.id} className="bg-gray-900 text-gray-200">
                {model.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Save button */}
      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 text-sm font-medium hover:bg-cyan-500/25 disabled:opacity-50 transition-colors"
        >
          {saving ? (
            <Loader className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          Save Default
        </button>
      </div>
    </div>
  );
}
