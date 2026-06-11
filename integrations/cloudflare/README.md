# Secure remote access to Archon via Cloudflare

This exposes Archon at **`https://archon.persalto.io`** so remote/partner-facility
development environments get full access to the knowledge base and **all Archon MCP
tools** — without putting Archon on the public internet unprotected.

Access is restricted to **explicitly-approved machines** using **Cloudflare Access
service tokens** (a per-machine credential file). There is **no SSO / no human login** on
this application: a request without a valid, listed token gets **HTTP 403** on every path.
This is the entire security boundary (Archon itself has no built-in auth), so the gate is
enforced at the Cloudflare edge before any traffic reaches the tunnel.

> Why not MAC addresses? A MAC address is a layer-2 identifier that never leaves the local
> network segment — Cloudflare never sees it. A per-machine service token is the
> internet-routable equivalent of "an identity file placed on the approved machine," and it
> is revocable per machine.

## Architecture

```
Remote machine ── HTTPS + CF-Access-Client-Id/Secret headers ──► Cloudflare edge
                                                                   │
                                              Cloudflare Access (service-token gate; 403 if absent)
                                                                   │
                                                  Tunnel: archon-persalto (cfargotunnel)
                                                                   │
                                  cloudflared container on the Archon host (app-network)
                                       /mcp, /archon-setup ─► archon-mcp:8051
                                       /api, /socket.io     ─► archon-server:8181
                                       /agents              ─► archon-agents:8052
                                       (everything else)    ─► archon-ui:3737
```

The tunnel daemon runs as the `cloudflared` service in the Archon `docker-compose.yml`
under the **`tunnel`** profile, so it reaches the other containers by name on `app-network`.

## Server-side resources (already provisioned)

| Resource | Value |
|---|---|
| Public hostname | `archon.persalto.io` |
| Cloudflare zone | `persalto.io` (`66f1b9309b25bb65ab691a0483acf144`) |
| Account | Trezero (`0b7d745203c82b5866aa75ef74bb8def`) |
| Tunnel name / id | `archon-persalto` / `0d035a48-2574-4af5-8c29-5da306fa9eb9` |
| Access app | `Archon` (`1082b663-fc56-4a98-8334-aa648815450a`) |
| Access policy | `approved-machines` (decision: `non_identity` / service-auth) |
| Access AUD | `b611b0eeeac7d8e22ba9f82bc0f91effc4868a526659523f798199d1286b2448` |

Credentials are **not** stored in this repo:
- The cloudflared `TUNNEL_TOKEN` lives in the gitignored `.env` as `ARCHON_TUNNEL_TOKEN`.
- The Cloudflare **API** token (`CF_API_TOKEN`/`CF_ACCOUNT_ID`) used by the script lives in
  `/mnt/e/Projects/persalto-operating-space/cloudflare.persalto.env.local` (gitignored).

## Operating the tunnel (on the Archon host)

```bash
docker compose --profile tunnel up -d cloudflared   # start
docker compose logs -f cloudflared                  # logs (look for "Registered tunnel connection")
docker compose restart cloudflared                  # restart
docker compose stop cloudflared                     # stop (Access stays; hostname goes 5xx until restarted)
```

If the tunnel won't register, give it ~30s (new tunnels propagate). The default `quic`
protocol works here; only switch to `--protocol http2` if QUIC/UDP is blocked on a network.

## Provision a remote machine (headless, over SSH)

From the Archon host (needs `curl`, `jq`, `ssh`, and the Cloudflare API env file):

```bash
integrations/cloudflare/provision-machine.sh --machine lab-jetson-01 --ssh user@remotehost
```

This mints a service token named `archon-lab-jetson-01`, adds it to the `approved-machines`
policy, and writes to the remote machine (chmod 600, never echoed):
- `~/.config/archon/cf-access.env` — `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` / `ARCHON_URL`
- `~/.config/archon/archon.mcp.json` — ready-to-use MCP server config

No SSH access yet? Use `--print-only` to print the credential + MCP snippet and place them
yourself.

### Wire up the tools on the remote machine

- **MCP (Claude Code / Cursor):** copy `~/.config/archon/archon.mcp.json` to your project's
  `.mcp.json` (it points at `https://archon.persalto.io/mcp` with the token headers).
- **REST / scanner / setup downloads:** send the two headers on every call:
  ```bash
  source ~/.config/archon/cf-access.env
  curl -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
       -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
       "$ARCHON_URL/api/health"            # expect 200
  ```
- **Browser UI without SSO (optional, still machine-only):** install `cloudflared` on the
  remote machine and run a local authenticated forwarder, then browse `http://localhost:8080`:
  ```bash
  source ~/.config/archon/cf-access.env
  cloudflared access tcp --hostname archon.persalto.io --url localhost:8080 \
    --service-token-id "$CF_ACCESS_CLIENT_ID" --service-token-secret "$CF_ACCESS_CLIENT_SECRET"
  ```

## Revoke a machine

```bash
integrations/cloudflare/provision-machine.sh --machine lab-jetson-01 --revoke
```

Removes the token from the policy and deletes it — enforced at the edge immediately. (A
token cannot be deleted while still referenced by the policy, so the script removes the
reference first. The policy must always retain at least one token.)

## Security notes

- A leaked token grants full Archon access from that one credential — tokens are per-machine
  (limited blast radius), stored `chmod 600`, never committed, and individually revocable.
- The Access app covers **all paths**; the `non_identity` policy means no SSO redirect — a
  missing/invalid token is a clean 403. Re-verify after any change:
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' https://archon.persalto.io/mcp           # 403 (no token)
  curl -s -o /dev/null -w '%{http_code}\n' -H "CF-Access-Client-Id: …" \
       -H "CF-Access-Client-Secret: …" https://archon.persalto.io/api/health        # 200
  ```
- The `archon-test` service token was created during setup as a validation identity and is
  currently the only token in the policy. To remove it, first provision a real machine
  (so the policy keeps >=1 token), then run `provision-machine.sh --machine test --revoke`
  (token name `archon-test`). The script refuses to remove the last remaining token.
