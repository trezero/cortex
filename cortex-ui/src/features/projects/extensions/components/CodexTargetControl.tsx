import { Code2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useToast } from "@/features/shared/hooks/useToast";
import { Button } from "@/features/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/features/ui/primitives/dialog";
import { useReviewExtensionTarget } from "../hooks/useExtensionQueries";
import type { Extension } from "../types";

const STATE_STYLE = {
  current: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  stale: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  pending: "border-zinc-600 bg-zinc-800 text-zinc-300",
  invalid: "border-red-500/30 bg-red-500/10 text-red-300",
};

export function CodexTargetControl({ extension }: { extension: Extension }) {
  const target = extension.targets?.find((item) => item.agent === "codex");
  const state = target?.compatibility_state ?? "pending";
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"direct" | "adapted">(target?.mode ?? "direct");
  const [scope, setScope] = useState<"repository" | "global">(target?.scope ?? "repository");
  const [adaptedContent, setAdaptedContent] = useState("");
  const review = useReviewExtensionTarget();
  const { showToast } = useToast();

  useEffect(() => {
    if (open) {
      setMode(target?.mode ?? "direct");
      setScope(target?.scope ?? "repository");
      setAdaptedContent("");
    }
  }, [open, target?.mode, target?.scope]);

  const submit = async () => {
    try {
      await review.mutateAsync({
        extensionId: extension.id,
        agent: "codex",
        mode,
        scope,
        reviewedBy: "cortex-ui",
        adaptedContent: mode === "adapted" ? adaptedContent : undefined,
        expectedSourceHash: extension.source_digest ?? extension.content_hash,
      });
      showToast(`Published Codex target for ${extension.name}`, "success");
      setOpen(false);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Failed to publish Codex target", "error");
    }
  };

  return (
    <>
      <div className="flex items-center gap-1.5">
        <span
          className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${STATE_STYLE[state]}`}
          title={`Codex compatibility: ${state}`}
        >
          <Code2 className="h-3 w-3" />
          Codex {state}
        </span>
        {target && (
          <span className="text-[10px] text-zinc-500">
            {target.mode} / {target.scope}
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="p-1 text-zinc-500 transition-colors hover:text-cyan-300"
          title={target ? "Review Codex target" : "Add Codex target"}
          aria-label={target ? "Review Codex target" : "Add Codex target"}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Codex Target: {extension.display_name || extension.name}</DialogTitle>
            <DialogDescription>
              Publish a reviewed Codex payload tied to source digest{" "}
              {(extension.source_digest ?? extension.content_hash).slice(0, 12)}.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-xs text-zinc-400">
              <span>Payload</span>
              <select
                value={mode}
                onChange={(event) => setMode(event.target.value as "direct" | "adapted")}
                className="h-9 w-full rounded border border-white/10 bg-zinc-900 px-2 text-sm text-white"
              >
                <option value="direct">Direct</option>
                <option value="adapted">Adapted</option>
              </select>
            </label>
            <label className="space-y-1 text-xs text-zinc-400">
              <span>Install scope</span>
              <select
                value={scope}
                onChange={(event) => setScope(event.target.value as "repository" | "global")}
                className="h-9 w-full rounded border border-white/10 bg-zinc-900 px-2 text-sm text-white"
              >
                <option value="repository">Repository</option>
                <option value="global">Global</option>
              </select>
            </label>
          </div>

          {mode === "adapted" && (
            <label className="space-y-1 text-xs text-zinc-400">
              <span>Adapted SKILL.md</span>
              <textarea
                value={adaptedContent}
                onChange={(event) => setAdaptedContent(event.target.value)}
                className="min-h-64 w-full resize-y rounded border border-white/10 bg-zinc-950 p-3 font-mono text-xs text-zinc-200"
                spellCheck={false}
              />
            </label>
          )}

          <div className="flex justify-end gap-2 border-t border-white/10 pt-3">
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={review.isPending} disabled={mode === "adapted" && !adaptedContent.trim()}>
              Publish
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
