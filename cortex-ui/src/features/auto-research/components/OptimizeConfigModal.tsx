import { useId, useState } from "react";
import { Button } from "../../ui/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/primitives/dialog";
import { useStartOptimization } from "../hooks/useAutoResearchQueries";

interface OptimizeConfigModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  suiteId: string;
  suiteName: string;
  onJobStarted: (jobId: string) => void;
}

export function OptimizeConfigModal({
  open,
  onOpenChange,
  suiteId,
  suiteName,
  onJobStarted,
}: OptimizeConfigModalProps) {
  const [maxIterations, setMaxIterations] = useState(10);
  const [modelOverride, setModelOverride] = useState("");
  const startOptimization = useStartOptimization();
  const iterationBudgetId = useId();
  const modelOverrideId = useId();

  const handleStart = async () => {
    const result = await startOptimization.mutateAsync({
      eval_suite_id: suiteId,
      max_iterations: maxIterations,
      model: modelOverride.trim() || null,
    });
    onOpenChange(false);
    onJobStarted(result.job_id);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Optimize: {suiteName}</DialogTitle>
          <DialogDescription>Configure the optimization run parameters.</DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* Iteration budget */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-200" htmlFor={iterationBudgetId}>
              Iteration Budget: <span className="text-cyan-400 font-bold">{maxIterations}</span>
            </label>
            <input
              id={iterationBudgetId}
              type="range"
              min={1}
              max={50}
              value={maxIterations}
              onChange={(e) => setMaxIterations(Number(e.target.value))}
              className="w-full accent-cyan-400"
            />
            <div className="flex justify-between text-xs text-zinc-500">
              <span>1</span>
              <span>50</span>
            </div>
          </div>

          {/* Model override */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-200" htmlFor={modelOverrideId}>
              Model Override
            </label>
            <input
              id={modelOverrideId}
              type="text"
              placeholder="Leave empty for default"
              value={modelOverride}
              onChange={(e) => setModelOverride(e.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm bg-black/30 border border-zinc-700 text-gray-100 placeholder-zinc-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50"
            />
          </div>

          {/* Note */}
          <p className="text-xs text-zinc-500">~3 LLM calls per iteration</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={startOptimization.isPending}>
            Cancel
          </Button>
          <Button
            variant="default"
            onClick={handleStart}
            loading={startOptimization.isPending}
            disabled={startOptimization.isPending}
          >
            Start
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
