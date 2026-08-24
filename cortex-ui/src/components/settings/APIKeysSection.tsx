import { KeyRound } from "lucide-react";

import { Card } from "../ui/Card";

/**
 * Cortex no longer accepts provider secrets from browser JavaScript. Provider
 * credentials are provisioned by an operator through the approved Atlas
 * 1Password workflow and exposed to services only at runtime.
 */
export const APIKeysSection = () => (
  <div className="space-y-5">
    <Card accentColor="pink" className="space-y-3">
      <div className="flex items-center gap-2">
        <KeyRound className="h-5 w-5 text-pink-500" />
        <h3 className="text-lg font-semibold">Provider credentials</h3>
      </div>
      <p className="text-sm text-gray-600 dark:text-zinc-400">
        Browser-side credential editing is disabled. Provider keys and service
        tokens are managed in the approved Atlas 1Password vault and injected
        only into authorized Cortex services at runtime.
      </p>
      <p className="text-sm text-gray-600 dark:text-zinc-400">
        Ask an Atlas operator to add, rotate, or revoke a provider credential.
        This page never downloads or displays secret values.
      </p>
    </Card>
  </div>
);
