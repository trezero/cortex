/**
 * ChatInput - Text area with model selector chip, action mode toggle,
 * and send button.
 *
 * Shift+Enter inserts a newline; Enter sends the message.
 * Disabled state when the agent service is unavailable or currently streaming.
 */

import { Lock, Send, Unlock } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { cn } from "../../../lib/utils";
import { ModelSelector } from "./ModelSelector";

interface ChatInputProps {
  onSend: (message: string) => void;
  isStreaming: boolean;
  disabled?: boolean;
  model: string;
  onModelChange: (model: string) => void;
  actionMode: boolean;
  onActionModeChange: (enabled: boolean) => void;
}

export function ChatInput({
  onSend,
  isStreaming,
  disabled = false,
  model,
  onModelChange,
  actionMode,
  onActionModeChange,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isDisabled = disabled || isStreaming;
  const canSend = value.trim().length > 0 && !isDisabled;

  const handleSend = useCallback(() => {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [canSend, onSend, value]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // Auto-resize textarea
  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  return (
    <div
      className={cn(
        "border-t border-white/10 bg-black/20 p-3",
        isDisabled && "opacity-60",
      )}
    >
      {/* Text area */}
      <div
        className={cn(
          "relative rounded-lg border transition-all duration-200",
          "backdrop-blur-xl bg-white/5",
          "border-white/10 focus-within:border-cyan-500/50",
          "focus-within:shadow-[0_0_15px_rgba(6,182,212,0.2)]",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={isDisabled}
          placeholder={isStreaming ? "Waiting for response..." : "Type a message..."}
          rows={1}
          className={cn(
            "w-full resize-none bg-transparent text-sm text-gray-200 placeholder:text-gray-600",
            "px-3 pt-3 pb-10 focus:outline-none",
            "disabled:cursor-not-allowed",
          )}
        />

        {/* Bottom toolbar */}
        <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between px-2 py-1.5">
          <div className="flex items-center gap-2">
            <ModelSelector value={model} onChange={onModelChange} />

            {/* Action mode toggle */}
            <button
              type="button"
              onClick={() => onActionModeChange(!actionMode)}
              title={actionMode ? "Action mode: requires approval" : "Action mode: auto-approve"}
              className={cn(
                "flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium transition-all duration-200",
                actionMode
                  ? "bg-amber-500/15 border border-amber-500/30 text-amber-300"
                  : "bg-white/5 border border-white/10 text-gray-500 hover:text-gray-400",
              )}
            >
              {actionMode ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
              {actionMode ? "Locked" : "Auto"}
            </button>
          </div>

          {/* Send button */}
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            className={cn(
              "p-1.5 rounded-md transition-all duration-200",
              canSend
                ? "text-cyan-400 hover:bg-cyan-500/20 hover:shadow-[0_0_10px_rgba(6,182,212,0.3)]"
                : "text-gray-600 cursor-not-allowed",
            )}
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
