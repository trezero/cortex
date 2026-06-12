import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "../../ui/primitives/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../../ui/primitives/tooltip";
import { OptimizeConfigModal } from "./OptimizeConfigModal";

interface OptimizeButtonProps {
  suiteId: string;
  suiteName: string;
  disabled?: boolean;
  onJobStarted: (jobId: string) => void;
}

export function OptimizeButton({ suiteId, suiteName, disabled, onJobStarted }: OptimizeButtonProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const button = (
    <Button
      variant="default"
      size="sm"
      disabled={disabled}
      onClick={() => !disabled && setModalOpen(true)}
      className="w-full mt-3"
    >
      <Sparkles className="w-4 h-4 mr-2" aria-hidden="true" />
      Optimize
    </Button>
  );

  return (
    <>
      {disabled ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block">{button}</span>
          </TooltipTrigger>
          <TooltipContent>
            <p>An optimization job is already running</p>
          </TooltipContent>
        </Tooltip>
      ) : (
        button
      )}
      <OptimizeConfigModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        suiteId={suiteId}
        suiteName={suiteName}
        onJobStarted={onJobStarted}
      />
    </>
  );
}
