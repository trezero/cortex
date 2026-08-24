# Cortex MCP connection

Cortex MCP is an authenticated service available only on the private VPN.

- MCP URL: `http://172.16.1.230:8051/mcp`
- Health URL: `http://172.16.1.230:8051/health`
- Transport: streamable HTTP
- Authentication: bearer token or `X-Cortex-Service-Token`

Load `CORTEX_MCP_AUTH_TOKEN` at runtime from the `Cortex MCP Service Token`
item in the approved Atlas 1Password vault. Never paste or render its value into
configuration, Markdown, logs, or shell history.

For Claude Code, preserve the environment placeholder:

```bash
claude mcp add --transport http -s local cortex http://172.16.1.230:8051/mcp \
  --header 'X-Cortex-Service-Token: ${CORTEX_MCP_AUTH_TOKEN}'
```

For Codex, run the operating-space portable setup. It merges one managed
`[mcp_servers.cortex]` table into the host-wide configuration and installs a
runtime 1Password-backed header helper. It does not persist the token.

Unauthorized MCP initialization must return `401`. Health remains public inside
the VPN. If the VPN or Cortex is unavailable, use repository-local plans,
documentation, and task records; Cortex is optional support tooling.
