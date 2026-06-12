import { useState } from "react";
import { Check, Copy, Download, Terminal } from "lucide-react";

type Platform = "unix" | "cmd" | "powershell";

const PLATFORMS: { key: Platform; label: string }[] = [
  { key: "unix", label: "Mac / Linux / WSL" },
  { key: "cmd", label: "Windows CMD" },
  { key: "powershell", label: "PowerShell" },
];

function getSetupCommand(platform: Platform, mcpHost: string): string {
  const mcpUrl = `http://${mcpHost}:8051`;
  switch (platform) {
    case "unix":
      return `curl -s ${mcpUrl}/cortex-setup.sh | bash`;
    case "cmd":
      return `curl.exe -o cortexSetup.bat ${mcpUrl}/cortex-setup.bat`;
    case "powershell":
      return `curl.exe -o cortexSetup.bat ${mcpUrl}/cortex-setup.bat; cmd /c cortexSetup.bat`;
  }
}

export function CortexSetupDownload() {
  const [platform, setPlatform] = useState<Platform>("unix");
  const [copied, setCopied] = useState(false);

  const mcpHost = window.location.hostname || "localhost";
  const command = getSetupCommand(platform, mcpHost);

  const handleCopy = async () => {
    try {
      // navigator.clipboard requires HTTPS or localhost — fails on plain HTTP LAN access
      await navigator.clipboard.writeText(command);
    } catch {
      // Fallback: create a temporary textarea and use execCommand
      const textarea = document.createElement("textarea");
      textarea.value = command;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
          <Terminal className="w-5 h-5 text-cyan-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-white mb-1">Connect a New Machine</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Run this command in your project directory to add Cortex to Claude Code and install the{" "}
            <code className="text-cyan-300 bg-white/5 px-1 rounded">/cortex-setup</code> command.
          </p>

          {/* Platform tabs */}
          <div className="flex gap-1 mb-3 bg-white/5 rounded-lg p-1 w-fit">
            {PLATFORMS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setPlatform(key)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  platform === key
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    : "text-zinc-400 hover:text-zinc-300 border border-transparent"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Command box */}
          <div className="relative group">
            <pre className="bg-black/40 border border-white/10 rounded-lg px-4 py-3 pr-12 text-sm text-cyan-300 font-mono overflow-x-auto whitespace-pre-wrap break-all">
              {command}
            </pre>
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2 p-1.5 rounded-md bg-white/5 border border-white/10 text-zinc-400 hover:text-white hover:bg-white/10 transition-colors"
              title="Copy to clipboard"
            >
              {copied ? (
                <Check className="w-4 h-4 text-green-400" />
              ) : (
                <Copy className="w-4 h-4" />
              )}
            </button>
          </div>

          {/* Download links as secondary option */}
          <div className="flex items-center gap-4 mt-3">
            <span className="text-xs text-zinc-500">Or download directly:</span>
            <a
              href="/cortex-setup.sh"
              download="cortexSetup.sh"
              className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-cyan-400 transition-colors"
            >
              <Download className="w-3 h-3" />
              .sh
            </a>
            <a
              href="/cortex-setup.bat"
              download="cortexSetup.bat"
              className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-cyan-400 transition-colors"
            >
              <Download className="w-3 h-3" />
              .bat
            </a>
          </div>

          <p className="text-xs text-zinc-500 mt-3">
            Then open Claude Code in your project and run{" "}
            <code className="text-cyan-400">/cortex-setup</code> to register your system and install
            extensions.
          </p>
        </div>
      </div>
    </div>
  );
}
