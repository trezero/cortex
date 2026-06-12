import { Clock, FileText, Sparkles } from "lucide-react";
import { useId, useState } from "react";
import { cn } from "../../ui/primitives/styles";
import { useAutoResearchJobs, useEvalSuites } from "../hooks/useAutoResearchQueries";
import type { AutoResearchJob } from "../types";
import { JobProgressModal } from "./JobProgressModal";
import { OptimizeButton } from "./OptimizeButton";

function statusBadge(status: AutoResearchJob["status"]) {
  const map: Record<AutoResearchJob["status"], string> = {
    running: "text-cyan-400 bg-cyan-400/10 border-cyan-400/30",
    completed: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
    failed: "text-red-400 bg-red-400/10 border-red-400/30",
    cancelled: "text-zinc-400 bg-zinc-400/10 border-zinc-400/30",
  };
  return <span className={cn("text-xs px-2 py-0.5 rounded border capitalize", map[status])}>{status}</span>;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AutoResearchPage() {
  const { data: suitesData, isLoading: suitesLoading } = useEvalSuites();
  const { data: jobsData, isLoading: jobsLoading } = useAutoResearchJobs();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const suitesHeadingId = useId();
  const jobsHeadingId = useId();

  const suites = suitesData?.suites ?? [];
  const jobs = jobsData?.jobs ?? [];

  // Determine which suite IDs have an active running job
  const runningJobSuiteIds = new Set(jobs.filter((j) => j.status === "running").map((j) => j.eval_suite_id));

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-cyan-400" aria-hidden="true" />
            Auto Research
          </h1>
          <p className="mt-1 text-sm text-zinc-400">Iterative prompt optimization engine</p>
        </div>
        {jobs.some((j) => j.status === "running") && (
          <span className="text-xs px-2 py-1 rounded border text-cyan-400 bg-cyan-400/10 border-cyan-400/30 animate-pulse">
            Job running…
          </span>
        )}
      </div>

      {/* Eval Suites Section */}
      <section aria-labelledby={suitesHeadingId}>
        <h2 id={suitesHeadingId} className="text-lg font-semibold text-gray-100 mb-4">
          Available Eval Suites
        </h2>

        {suitesLoading && <p className="text-sm text-zinc-400">Loading suites…</p>}

        {!suitesLoading && suites.length === 0 && (
          <div className="rounded-lg border border-zinc-800/50 bg-gradient-to-b from-white/5 to-black/10 p-8 backdrop-blur-md text-center">
            <FileText className="w-8 h-8 text-zinc-600 mx-auto mb-3" aria-hidden="true" />
            <p className="text-sm text-zinc-400">No eval suites configured.</p>
          </div>
        )}

        {suites.length > 0 && (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {suites.map((suite) => (
              <div
                key={suite.id}
                className="rounded-lg border border-zinc-800/50 bg-gradient-to-b from-white/5 to-black/10 p-4 backdrop-blur-md flex flex-col"
              >
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-100 truncate">{suite.name}</h3>
                  {suite.description && <p className="text-xs text-zinc-400 mt-1 line-clamp-2">{suite.description}</p>}
                  <div className="mt-3 space-y-1">
                    <div className="flex items-center gap-1.5 text-xs text-zinc-500 truncate">
                      <FileText className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                      <span className="truncate font-mono">{suite.target_file}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                      <Clock className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                      <span>{suite.test_case_count} test cases</span>
                    </div>
                  </div>
                </div>

                <OptimizeButton
                  suiteId={suite.id}
                  suiteName={suite.name}
                  disabled={runningJobSuiteIds.has(suite.id)}
                  onJobStarted={(jobId) => setSelectedJobId(jobId)}
                />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Recent Jobs Section */}
      <section aria-labelledby={jobsHeadingId}>
        <h2 id={jobsHeadingId} className="text-lg font-semibold text-gray-100 mb-4">
          Recent Jobs
        </h2>

        {jobsLoading && <p className="text-sm text-zinc-400">Loading jobs…</p>}

        {!jobsLoading && jobs.length === 0 && (
          <div className="rounded-lg border border-zinc-800/50 bg-gradient-to-b from-white/5 to-black/10 p-6 backdrop-blur-md text-center">
            <p className="text-sm text-zinc-400">No optimization jobs yet. Run an eval suite to get started.</p>
          </div>
        )}

        {jobs.length > 0 && (
          <div className="rounded-lg border border-zinc-800/50 bg-gradient-to-b from-white/5 to-black/10 backdrop-blur-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/40">
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Suite</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Best Score</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Iterations</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Started</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="border-b border-zinc-800/50 last:border-0 hover:bg-white/5 cursor-pointer transition-colors"
                    onClick={() => setSelectedJobId(job.id)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && setSelectedJobId(job.id)}
                  >
                    <td className="px-4 py-3 text-zinc-200 font-mono text-xs truncate max-w-[160px]">
                      {job.eval_suite_id}
                    </td>
                    <td className="px-4 py-3">{statusBadge(job.status)}</td>
                    <td className="px-4 py-3 font-mono text-zinc-100">
                      {job.best_score !== null ? job.best_score.toFixed(3) : "—"}
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      {job.completed_iterations} / {job.max_iterations}
                    </td>
                    <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">{formatDate(job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Job Progress Modal */}
      <JobProgressModal jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
    </div>
  );
}
