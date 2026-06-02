# Postman Setup

How to obtain the **Postman API Key** and **Workspace ID** needed by Archon's Postman integration, and where to enter them.

---

## 1. Get Your Postman API Key

1. Sign in to Postman at **https://web.postman.co**.
2. Click your **profile avatar** in the top-right corner → choose **Settings**.
   (Direct link: **https://web.postman.co/settings/me/api-keys**)
3. In the left sidebar of the Settings page, click **API keys**.
4. Click **Generate API Key**.
5. Give it a descriptive name (e.g. `Archon Integration`) and click **Generate API Key**.
6. **Copy the key immediately** — Postman shows it only once. If you lose it, you must generate a new one.

### Expected format

A valid Postman API key always:
- Starts with the literal prefix `PMAK-`
- Followed by **24 lowercase hex characters**, a dash, then **34 lowercase hex characters**

**Example (fake — do not use):**

```
PMAK-1a2b3c4d5e6f7a8b9c0d1e2f-3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f
```

If your key is missing the `PMAK-` prefix, or has spaces, line breaks, or extra characters — it is invalid.

---

## 2. Get Your Workspace ID

1. In Postman, open the **workspace** you want Archon to write collections into.
2. Click the **workspace name** at the top of the left sidebar → choose **Settings**.
   (Or: top-right gear icon while inside the workspace → **Workspace settings**.)
3. Scroll to the **Workspace ID** field at the bottom of the General tab and click the **copy** icon.

**Alternative — get it from the URL:**

When viewing a workspace, the browser URL looks like:

```
https://web.postman.co/workspace/My-Workspace~973f9526-5d90-4f75-a0fb-b4b510ccc6ef/...
```

The workspace ID is the part **after the `~`** — in this example: `973f9526-5d90-4f75-a0fb-b4b510ccc6ef`.

> **IMPORTANT:** Do **NOT** include the workspace name or the `~` separator. Paste **only the UUID**.

### Expected format

A valid workspace ID is a **standard UUID v4** — 36 characters total, formatted as `8-4-4-4-12` hex digits separated by dashes:

**Example (fake — do not use):**

```
973f9526-5d90-4f75-a0fb-b4b510ccc6ef
```

**Invalid examples to watch out for:**

| Bad value | Why it's wrong |
|-----------|---------------|
| `My-Workspace~973f9526-5d90-4f75-a0fb-b4b510ccc6ef` | Has workspace name + `~` prefix — strip it |
| `973f95265d904f75a0fbb4b510ccc6ef` | Missing dashes |
| `https://web.postman.co/workspace/...` | Full URL pasted instead of just the ID |

---

## 3. Enter the Values into Archon

1. Open the Archon UI (e.g. `http://172.16.1.230:3737`).
2. Go to **Settings** → **API Keys / Credentials**.
3. Add (or update) these two credentials:
   - `POSTMAN_API_KEY` — paste the `PMAK-…` key. Mark it **Encrypted**.
   - `POSTMAN_WORKSPACE_ID` — paste **only the UUID**. Plaintext (not encrypted).
4. Save.

No backend restart is needed — credentials are read on each Postman MCP call.

---

## 4. Verify

In any project, ask Claude:

> "Run `find_postman` and tell me the sync_mode and workspace."

A correct configuration returns `sync_mode: "api"` and resolves the workspace name back from the UUID. An incorrect workspace ID returns a 404 from `api.getpostman.com`.
