# Cortex Setup Agent

**Agent Name:** cortexSetup  
**Version:** 1.0  
**Type:** Environment Configuration Agent

## Purpose

Automate Cortex environment setup including local Supabase configuration, Docker validation, service deployment, and MCP integration.

## Capabilities

- Detect and configure local Supabase instances
- Validate and fix Docker credential issues (WSL)
- Generate .env files with proper configuration
- Deploy Cortex services via Docker Compose
- Verify service health
- Configure Cortex MCP server in Kiro CLI

## Usage

```bash
# Run setup for new Cortex instance
kiro-cli chat --agent cortexSetup
```

## Workflow

1. Detect local Supabase instance configuration
2. Check Docker credential configuration
3. Generate .env file with Supabase credentials
4. Deploy services with docker compose
5. Verify service health
6. Configure MCP server integration
7. Provide next steps (database migration)

## Integration

- Reads from `../localSupabase/supabase-instance-config.json`
- Writes to `.env`
- Modifies `~/.docker/config.json` if needed
- Updates `~/.config/kiro-cli/mcp_config.json`
