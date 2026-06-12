# Cortex Development Patterns

## Docker Credential Fix (WSL)

**Problem:** Docker credential helper fails with "exec format error" in WSL when using Windows Docker Desktop.

**Solution:**
```bash
# Remove problematic credential store setting
sed -i 's/"credsStore": "desktop.exe"/"credsStore": ""/g' ~/.docker/config.json
```

**When to use:** Before running `docker compose` commands if you see credential-related errors.

## Local Supabase Configuration

**Pattern:** Use `host.docker.internal` for Docker containers to access local Supabase:
```bash
SUPABASE_URL=http://host.docker.internal:8001
```

**Rationale:** Allows Cortex containers to reach Supabase running on host machine.

## Service Health Verification

**Pattern:** Check Cortex service status after deployment:
```bash
docker ps --filter "name=cortex" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## MCP Server Configuration

**Pattern:** Configure Cortex MCP in Kiro CLI:
```json
{
  "mcpServers": {
    "cortex": {
      "command": "npx",
      "args": ["mcp-remote", "http://HOST:8051/mcp", "--allow-http"]
    }
  }
}
```

**Location:** `~/.config/kiro-cli/mcp_config.json`
