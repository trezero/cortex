import { Download, Wrench } from "lucide-react";

export function AgentWorkOrdersSetupDownload() {
  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
          <Wrench className="w-5 h-5 text-emerald-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-white mb-1">Agent Work Orders Setup</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Interactive CLI to configure, deploy, and verify the Agent Work Orders service.
            Includes a status dashboard, environment setup, database migrations, and service
            management.
          </p>
          <div className="flex flex-wrap gap-3 mb-4">
            <a
              href="/cortex-setup/agent-work-orders-setup.sh"
              download="agentWorkOrderSetup.sh"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm font-medium hover:bg-emerald-500/20 transition-colors"
            >
              <Download className="w-4 h-4" />
              agentWorkOrderSetup.sh
              <span className="text-xs text-zinc-500">Mac / Linux</span>
            </a>
          </div>
          <p className="text-xs text-zinc-500">
            Save to your project root and run{" "}
            <code className="text-emerald-400">bash agentWorkOrderSetup.sh</code> to get started.
          </p>
        </div>
      </div>
    </div>
  );
}
