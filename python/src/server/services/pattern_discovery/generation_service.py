"""YAML workflow generation from discovered patterns using Sonnet API."""

import os
from typing import Any

import anthropic

from ...config.logfire_config import get_logger

logger = get_logger(__name__)

GENERATION_MODEL = os.getenv("PATTERN_GENERATION_MODEL", "claude-sonnet-4-20250514")


class GenerationService:
    def __init__(self):
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def generate_workflow_yaml(self, pattern: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Generate a YAML workflow definition from a scored pattern.

        Sends pattern details to Sonnet to produce an Cortex-compatible YAML workflow.
        """
        try:
            client = self._get_client()
            prompt = self._build_generation_prompt(pattern)

            response = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            yaml_content = response.content[0].text
            # Extract YAML from potential markdown code fences
            if "```yaml" in yaml_content:
                yaml_content = yaml_content.split("```yaml")[1].split("```")[0].strip()
            elif "```" in yaml_content:
                yaml_content = yaml_content.split("```")[1].split("```")[0].strip()

            return True, {"yaml": yaml_content, "pattern_name": pattern.get("intent_key", "unnamed")}
        except Exception as e:
            logger.error(f"Error generating workflow YAML: {e}", exc_info=True)
            return False, {"error": str(e)}

    def _build_generation_prompt(self, pattern: dict[str, Any]) -> str:
        """Build the prompt for Sonnet to generate workflow YAML."""
        sequence = pattern.get("sequence", [])
        repos = pattern.get("repos", [])
        intent_key = pattern.get("intent_key", "")
        action_verb = pattern.get("action_verb", "")
        target_object = pattern.get("target_object", "")

        return f"""Generate an Cortex workflow YAML definition for this discovered pattern.

Pattern: {intent_key or f"{action_verb} {target_object}"}
Sequence: {sequence}
Observed in repos: {repos}
Frequency: {pattern.get('support', pattern.get('event_count', 'unknown'))} occurrences

The YAML should follow this structure:
```yaml
name: <workflow-name>
description: <what this workflow automates>
nodes:
  - id: <node-id>
    command: <what to execute>
    prompt: |
      <detailed prompt for the agent>
    depends_on: []  # or list of node IDs
    approval:
      required: false  # set true for risky steps
```

Generate a practical, production-ready workflow. Only output the YAML, no explanation."""
