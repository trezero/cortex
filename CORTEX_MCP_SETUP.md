# Cortex MCP Server - Connection Instructions

## Quick Setup

Add this to your `~/.config/kiro-cli/mcp_config.json`:

```json
{
  "mcpServers": {
    "cortex": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://172.16.1.203:8051/mcp",
        "--allow-http"
      ]
    }
  }
}
```

Then restart your Kiro CLI session.

## What You Get

Once connected, Kiro will have access to:

- **Knowledge Base Search**: Search crawled documentation and uploaded documents
- **Code Examples**: Find code snippets from the knowledge base
- **Project Management**: Create and manage projects
- **Task Management**: Create, update, and track tasks
- **Document Management**: Version-controlled project documents

## Verify Connection

After restarting Kiro, you can verify the connection by asking:
```
"Search the Cortex knowledge base for [topic]"
```

## Server Details

- **Host**: 172.16.1.203
- **Port**: 8051
- **Protocol**: HTTP (local network)
- **UI**: http://172.16.1.203:3737
- **API**: http://172.16.1.203:8181

## Troubleshooting

If connection fails:
1. Verify Cortex services are running: `docker ps --filter "name=cortex"`
2. Check network connectivity: `curl http://172.16.1.203:8051/health`
3. Ensure `mcp-remote` is available: `npx mcp-remote --version`
