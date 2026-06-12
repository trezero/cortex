import { AlertCircle, Check, TrendingUp } from "lucide-react";
import { Button } from "../../ui/primitives/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../ui/primitives/dialog";
import { cn } from "../../ui/primitives/styles";
import { useApplyResult, useAutoResearchJob, useCancelJob } from "../hooks/useAutoResearchQueries";
import type { AutoResearchIteration } from "../types";

interface JobProgressModalProps {
  jobId: string | null;
  onClose: () => void;
}

function statusLabel(status: string) {
  switch (status) {
    case "running":
      return (
        <span className="text-xs px-2 py-0.5 rounded border text-cyan-400 bg-cyan-400/10 border-cyan-400/30">
          Running
        </span>
      );
    case "completed":
      return (
        <span className="text-xs px-2 py-0.5 rounded border text-emerald-400 bg-emerald-400/10 border-emerald-400/30">
          Completed
        </span>
      );
    case "failed":
      return (
        <span className="text-xs px-2 py-0.5 rounded border text-red-400 bg-red-400/10 border-red-400/30">Failed</span>
      );
    case "cancelled":
      return (
        <span className="text-xs px-2 py-0.5 rounded border text-zinc-400 bg-zinc-400/10 border-zinc-400/30">
          Cancelled
        </span>
      );
    default:
      return (
        <span className="text-xs px-2 py-0.5 rounded border text-zinc-400 bg-zinc-400/10 border-zinc-400/30">
          {status}
        </span>
      );
  }
}

function signalsSummary(signals: AutoResearchIteration["signals"]) {
  const entries = Object.values(signals);
  const passing = entries.filter((s) => s.value).length;
  return `${passing}/${entries.length} passing`;
}

export function JobProgressModal({ jobId, onClose }: JobProgressModalProps) {
  const { data, isLoading } = useAutoResearchJob(jobId);
  const cancelJob = useCancelJob();
  const applyResult = useApplyResult();

  const job = data?.job;
  const isTerminal = job && ["completed", "failed", "cancelled"].includes(job.status);
  const progressPct = job
    ? job.max_iterations > 0
      ? Math.round((job.completed_iterations / job.max_iterations) * 100)
      : 0
    : 0;

  const hasImprovement =
    job?.status === "completed" &&
    job.best_score !== null &&
    job.baseline_score !== null &&
    job.best_score > job.baseline_score;

  const handleCancel = () => {
    if (jobId) cancelJob.mutate(jobId);
  };

  const handleApply = async () => {
    if (jobId) {
      await applyResult.mutateAsync(jobId);
      onClose();
    }
  };

  return (
    <Dialog open={!!jobId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Optimization Progress</DialogTitle>
        </DialogHeader>

        {isLoading && !job && (
          <div className="flex items-center justify-center py-12">
            <p className="text-zinc-400 text-sm">Loading job details...</p>
          </div>
        )}

        {job && (
          <div className="space-y-5">
            {/* Status + progress */}
            <div className="flex items-center gap-3">
              {statusLabel(job.status)}
              <span className="text-sm text-zinc-400">
                {job.completed_iterations} / {job.max_iterations} iterations
              </span>
            </div>

            {/* Progress bar */}
            <div className="w-full h-2 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  job.status === "completed" ? "bg-emerald-500" : "bg-cyan-500",
                  job.status === "failed" && "bg-red-500",
                )}
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="text-right text-xs text-zinc-500">{progressPct}%</div>

            {/* Improvement summary when completed */}
            {job.status === "completed" && job.baseline_score !== null && job.best_score !== null && (
              <div className="flex items-center gap-2 p-3 rounded-lg border border-zinc-700 bg-black/20">
                <TrendingUp className="w-4 h-4 text-cyan-400 shrink-0" aria-hidden="true" />
                <span className="text-sm text-zinc-300">
                  Baseline <span className="font-mono text-zinc-100">{job.baseline_score.toFixed(3)}</span>
                  {" → "}
                  Best{" "}
                  <span className={cn("font-mono font-bold", hasImprovement ? "text-emerald-400" : "text-zinc-100")}>
                    {job.best_score.toFixed(3)}
                  </span>
                  {hasImprovement && <Check className="inline ml-1 w-3 h-3 text-emerald-400" aria-hidden="true" />}
                </span>
              </div>
            )}

            {/* Error message */}
            {job.status === "failed" && job.error_message && (
              <div className="flex items-start gap-2 p-3 rounded-lg border border-red-400/30 bg-red-400/5">
                <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
                <p className="text-sm text-red-300">{job.error_message}</p>
              </div>
            )}

            {/* Iteration table */}
            {job.iterations && job.iterations.length > 0 && (
              <div className="overflow-x-auto rounded-lg border border-zinc-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 bg-zinc-900/50">
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400">#</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400">Score</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400">Frontier</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400">Signals</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.iterations.map((iter) => (
                      <tr
                        key={iter.id}
                        className={cn(
                          "border-b border-zinc-800/50 last:border-0 transition-colors",
                          iter.is_frontier ? "border-l-2 border-l-cyan-500 bg-cyan-500/5" : "hover:bg-zinc-800/30",
                        )}
                      >
                        <td className="px-3 py-2 text-zinc-300 font-mono">{iter.iteration_number}</td>
                        <td className="px-3 py-2 font-mono text-zinc-100">{iter.scalar_score.toFixed(3)}</td>
                        <td className="px-3 py-2">
                          {iter.is_frontier ? (
                            <span className="text-xs px-1.5 py-0.5 rounded border text-cyan-400 bg-cyan-400/10 border-cyan-400/30">
                              Yes
                            </span>
                          ) : (
                            <span className="text-zinc-600">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-zinc-400 text-xs">{signalsSummary(iter.signals)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {!isTerminal && (
            <Button
              variant="destructive"
              onClick={handleCancel}
              loading={cancelJob.isPending}
              disabled={cancelJob.isPending}
            >
              Cancel Job
            </Button>
          )}
          {job?.status === "completed" && !hasImprovement && (
            <span className="text-sm text-zinc-400 self-center">No improvement found</span>
          )}
          {job?.status === "completed" && hasImprovement && (
            <Button
              variant="default"
              onClick={handleApply}
              loading={applyResult.isPending}
              disabled={applyResult.isPending}
            >
              Apply Result
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
