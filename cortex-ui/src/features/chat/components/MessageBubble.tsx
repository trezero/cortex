/**
 * MessageBubble - Renders a single chat message with role-based styling.
 *
 * User messages are right-aligned with an accent background.
 * Assistant messages are left-aligned with a glassmorphic card and
 * Markdown rendering (syntax-highlighted code blocks, GFM tables, etc.).
 */

import { Check, Copy, User } from "lucide-react";
import { useCallback, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import "highlight.js/styles/atom-one-dark.min.css";
import { cn } from "../../../lib/utils";
import type { ChatMessage } from "../types";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

/** Format an ISO timestamp into a short locale time string */
function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/** Copy-to-clipboard button shown inside code blocks */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback ignored
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        "absolute top-2 right-2 p-1.5 rounded-md transition-all duration-200",
        "bg-white/10 hover:bg-white/20 text-gray-400 hover:text-gray-200",
        "opacity-0 group-hover/code:opacity-100",
      )}
      aria-label={copied ? "Copied" : "Copy code"}
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

/**
 * Custom Markdown component overrides for react-markdown.
 * Code blocks get syntax highlighting (via rehype-highlight) and a copy button.
 */
const markdownComponents: Components = {
  pre({ children, ...props }) {
    return (
      <pre
        {...props}
        className="group/code relative rounded-lg bg-black/40 border border-white/10 p-4 my-3 overflow-x-auto text-sm"
      >
        {children}
      </pre>
    );
  },
  code({ className, children, ...props }) {
    const isInline = !className;
    const codeString = String(children).replace(/\n$/, "");

    if (isInline) {
      return (
        <code
          {...props}
          className="rounded px-1.5 py-0.5 bg-white/10 border border-white/5 text-cyan-300 text-[0.85em]"
        >
          {children}
        </code>
      );
    }

    return (
      <>
        <code {...props} className={className}>
          {children}
        </code>
        <CopyButton text={codeString} />
      </>
    );
  },
  a({ href, children, ...props }) {
    return (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
      >
        {children}
      </a>
    );
  },
  table({ children, ...props }) {
    return (
      <div className="overflow-x-auto my-3">
        <table {...props} className="min-w-full border border-white/10 text-sm">
          {children}
        </table>
      </div>
    );
  },
  th({ children, ...props }) {
    return (
      <th {...props} className="border border-white/10 bg-white/5 px-3 py-1.5 text-left font-medium">
        {children}
      </th>
    );
  },
  td({ children, ...props }) {
    return (
      <td {...props} className="border border-white/10 px-3 py-1.5">
        {children}
      </td>
    );
  },
};

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const content = message.content ?? "";

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "relative max-w-[80%] rounded-lg px-4 py-3",
          isUser
            ? // User: accent purple background
              "bg-gradient-to-br from-purple-500/20 to-purple-600/10 border border-purple-500/30"
            : // Assistant: glassmorphic card
              "backdrop-blur-xl bg-white/5 border border-white/10",
        )}
      >
        {/* Header: role icon + timestamp */}
        <div className="flex items-center gap-2 mb-1.5">
          {isUser ? (
            <User className="w-3.5 h-3.5 text-purple-400" />
          ) : (
            <img src="/logo-neon.png" alt="Cortex" className="w-3.5 h-3.5" />
          )}
          <span className="text-[11px] text-gray-500 dark:text-zinc-500">{formatTimestamp(message.created_at)}</span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-[11px] text-cyan-400">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              streaming
            </span>
          )}
        </div>

        {/* Content */}
        {isUser ? (
          <p className="text-sm text-gray-200 whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose prose-sm prose-invert max-w-none text-gray-200 prose-headings:text-gray-100 prose-strong:text-gray-100 prose-code:text-cyan-300">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={markdownComponents}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
