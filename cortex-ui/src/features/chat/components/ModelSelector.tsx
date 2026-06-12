/**
 * ModelSelector - Small dropdown chip for selecting the AI model.
 *
 * Displays the current model name as a compact chip. Clicking it reveals
 * a dropdown of available models.
 */

import { ChevronDown, Cpu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "../../../lib/utils";

interface ModelSelectorProps {
  value: string;
  onChange: (model: string) => void;
}

const AVAILABLE_MODELS = [
  { id: "openai:gpt-4o", label: "GPT-4o" },
  { id: "openai:gpt-4.1", label: "GPT-4.1" },
  { id: "openai:gpt-4.1-mini", label: "GPT-4.1 Mini" },
  { id: "anthropic:claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
  { id: "anthropic:claude-opus-4-20250514", label: "Claude Opus 4" },
  { id: "anthropic:claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
];

/** Get a short display name for a model ID */
function getModelLabel(modelId: string): string {
  const match = AVAILABLE_MODELS.find((m) => m.id === modelId);
  return match?.label ?? modelId;
}

export function ModelSelector({ value, onChange }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleSelect = useCallback(
    (modelId: string) => {
      onChange(modelId);
      setIsOpen(false);
    },
    [onChange],
  );

  // Close dropdown on outside click
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative">
      {/* Chip trigger */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all duration-200",
          "bg-white/5 border border-white/10 text-gray-400",
          "hover:bg-white/10 hover:text-gray-300 hover:border-cyan-500/30",
          isOpen && "border-cyan-500/50 text-cyan-300 bg-cyan-500/10",
        )}
      >
        <Cpu className="w-3 h-3" />
        <span className="truncate max-w-[120px]">{getModelLabel(value)}</span>
        <ChevronDown className={cn("w-3 h-3 transition-transform duration-200", isOpen && "rotate-180")} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className={cn(
            "absolute bottom-full left-0 mb-1 w-56 rounded-lg overflow-hidden z-50",
            "backdrop-blur-xl bg-gray-900/95 border border-white/10",
            "shadow-[0_0_20px_rgba(0,0,0,0.5)]",
          )}
        >
          {AVAILABLE_MODELS.map((model) => (
            <button
              key={model.id}
              type="button"
              onClick={() => handleSelect(model.id)}
              className={cn(
                "flex items-center gap-2 w-full px-3 py-2 text-left text-xs transition-colors",
                model.id === value
                  ? "bg-cyan-500/15 text-cyan-300"
                  : "text-gray-400 hover:bg-white/5 hover:text-gray-200",
              )}
            >
              <Cpu className="w-3.5 h-3.5 shrink-0" />
              <span>{model.label}</span>
              {model.id === value && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan-400" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
