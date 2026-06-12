# Telegram + Cortex Integration Ideas

**Date**: 2026-03-20
**Depends on**: Telegram per-project support PR (upstream to Anthropic)

## 1. cortexSetup Integration

Add an optional step to the Cortex setup process that configures a per-project Telegram bot:
- Prompt user: "Would you like to configure a Telegram bot for this project?"
- If yes, guide them through creating a bot via @BotFather
- Run the equivalent of `/telegram:configure --project <name> <token>`
- Handle pairing flow

## 2. claudePro Launcher Command

A convenience wrapper (shell script or alias) that simplifies launching Claude Code with project-specific configuration:

```bash
claudePro cortex        # cd ~/projects/Trinity/cortex && claude
claudePro rr            # cd ~/projects/reciperaiders && claude
```

Features:
- Maps short aliases to project directories
- Ensures TELEGRAM_PROJECT_ID and other project config is available
- Could be configured via a simple JSON/YAML mapping file
- Could be installed by cortexSetup

## 3. Multi-Project Dashboard

Future idea: A Telegram bot or group that shows status across all active Claude Code sessions/projects — which are running, last activity, etc.
