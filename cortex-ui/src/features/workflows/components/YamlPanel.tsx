import { useRef, useState } from "react";

interface YamlPanelProps {
  yaml: string;
  onYamlChange: (yaml: string) => void;
  parseError: string | null;
}

export function YamlPanel({ yaml, onYamlChange, parseError }: YamlPanelProps) {
  const [editMode, setEditMode] = useState(false);
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(yaml);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API may not be available in all contexts
    }
  }

  function toggleMode() {
    setEditMode((prev) => !prev);
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-gray-400">YAML Preview</h3>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleMode}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              editMode
                ? "bg-amber-600 hover:bg-amber-500 text-white"
                : "bg-white/10 hover:bg-white/15 text-gray-400"
            }`}
          >
            {editMode ? "Editing" : "Edit"}
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/15 text-gray-400 transition-colors"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      {parseError && (
        <div className="mb-2 px-3 py-2 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-400">
          {parseError}
        </div>
      )}

      {editMode ? (
        <textarea
          ref={textareaRef}
          value={yaml}
          onChange={(e) => onYamlChange(e.target.value)}
          spellCheck={false}
          className="flex-1 w-full bg-black/40 border border-white/10 rounded px-4 py-3 text-sm
            font-mono text-gray-300 focus:border-cyan-500 focus:outline-none transition-colors
            resize-none leading-relaxed"
        />
      ) : (
        <pre
          className="flex-1 w-full bg-black/40 border border-white/10 rounded px-4 py-3 text-sm
            font-mono text-gray-300 overflow-auto leading-relaxed whitespace-pre-wrap break-words"
        >
          {yaml || "# Empty workflow definition"}
        </pre>
      )}
    </div>
  );
}
