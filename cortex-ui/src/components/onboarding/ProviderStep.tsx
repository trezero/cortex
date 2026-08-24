import { useState } from "react";
import { Loader, Save } from "lucide-react";

import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import { useToast } from "../../features/shared/hooks/useToast";
import { credentialsService } from "../../services/credentialsService";

interface ProviderStepProps {
  onSaved: () => void;
  onSkip: () => void;
}

export const ProviderStep = ({ onSaved, onSkip }: ProviderStepProps) => {
  const [provider, setProvider] = useState("openai");
  const [saving, setSaving] = useState(false);
  const { showToast } = useToast();

  const saveProvider = async () => {
    setSaving(true);
    try {
      await credentialsService.updateCredential({
        key: "LLM_PROVIDER",
        value: provider,
        is_encrypted: false,
        category: "rag_strategy",
      });
      localStorage.setItem("onboardingDismissed", "true");
      showToast("Provider preference saved", "success");
      onSaved();
    } catch (error) {
      console.error("Failed to save provider preference:", error);
      showToast("Failed to save provider preference", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <Select
        label="Select AI Provider"
        value={provider}
        onChange={(event) => setProvider(event.target.value)}
        options={[
          { value: "openai", label: "OpenAI" },
          { value: "google", label: "Google Gemini" },
          { value: "ollama", label: "Ollama (Local)" },
        ]}
        accentColor="green"
      />
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
        <p className="text-sm text-blue-800 dark:text-blue-200">
          Provider secrets are managed by an Atlas operator in 1Password. This
          browser records only the non-secret provider preference.
        </p>
      </div>
      <div className="flex gap-3 pt-4">
        <Button
          variant="primary"
          size="lg"
          onClick={saveProvider}
          disabled={saving}
          icon={saving ? <Loader className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          className="flex-1"
        >
          {saving ? "Saving..." : "Save & Continue"}
        </Button>
        <Button variant="outline" size="lg" onClick={onSkip} disabled={saving} className="flex-1">
          Skip for Now
        </Button>
      </div>
    </div>
  );
};
