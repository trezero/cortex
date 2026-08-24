# Optional Cloudflare Access integration

Normal Cortex use is restricted to the private VPN and does not require HTTPS
or Cloudflare. The supported MCP endpoint is `http://172.16.1.230:8051/mcp`
with Cortex service-token authentication.

The existing `cortex.persalto.io` tunnel and Access application are retained as
dormant, reversible infrastructure only. Do not start the Compose `tunnel`
profile or provision an internet-routable client unless that exact remote-access
use is explicitly approved.

## Existing resources

| Resource | Value |
|---|---|
| Public hostname | `cortex.persalto.io` |
| Tunnel name / id | `cortex-persalto` / `0d035a48-2574-4af5-8c29-5da306fa9eb9` |
| Access app | `Cortex` / `1082b663-fc56-4a98-8334-aa648815450a` |
| Access policy | `approved-machines` |

The tunnel is off during VPN-only operation:

```bash
docker compose stop cloudflared
```

Starting it is an external-access change and requires explicit authorization:

```bash
docker compose --profile tunnel up -d cloudflared
```

## Provisioning an explicitly approved remote machine

The provisioner never prints a credential, writes a credential file, or sends a
credential over SSH. It uses only the operating-space 1Password service-account
wrapper, reads the Cloudflare API fields from `Cloudflare - trezero`, and writes
the new per-machine token directly into an Atlas-vault login item.

```bash
integrations/cloudflare/provision-machine.sh --machine lab-jetson-01 \
  --op-wrapper /path/to/persalto-operating-space/scripts/op_service_account.sh
```

The resulting item is named `Cortex Cloudflare Access - lab-jetson-01`. A client
must resolve that item and `Cortex MCP Service Token` at runtime; no literal
secret belongs in MCP configuration.

Revoke and archive the corresponding item with:

```bash
integrations/cloudflare/provision-machine.sh --machine lab-jetson-01 --revoke \
  --op-wrapper /path/to/persalto-operating-space/scripts/op_service_account.sh
```
