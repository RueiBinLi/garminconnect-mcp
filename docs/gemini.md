# Add Garmin Connect MCP to Gemini CLI

This server runs locally over stdio. It reads Garmin credentials from this repo's
`.env` file and stores Garmin tokens in `GARMINCONNECT_TOKEN_DIR`, or
`~/.garminconnect` when that variable is not set.

## One-time Garmin login

Run this first from a terminal so MFA prompts are visible:

```bash
cd /path/to/garminconnect-mcp
.venv/bin/garminconnect-mcp login
```

## Project-scoped Gemini CLI config

This repo includes `.gemini/settings.json`:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp",
      "args": [],
      "cwd": "/path/to/garminconnect-mcp",
      "timeout": 600000,
      "trust": false
    }
  }
}
```

When Gemini CLI starts in this project, it should discover the `garmin` MCP
server from `.gemini/settings.json`.

Check the connection with:

```bash
gemini mcp list
```

Inside Gemini CLI, use `/mcp` and test with `garmin_connection_status` or
`garmin_ping`. Do not use `garmin_profile` as a smoke test because it returns
private account data.

## User-scoped Gemini CLI config

Use `docs/gemini_settings.json` as the `~/.gemini/settings.json` body if you
want this MCP server available outside this repo.

You can also add the same server globally with Gemini CLI:

```bash
gemini mcp add --scope user garmin /path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp
```

Gemini CLI stores user-scoped settings at:

```text
~/.gemini/settings.json
```

## Privacy

Garmin responses are private health/account data. Use
`garmin_connection_status` or `garmin_ping` for connection checks, and avoid
pasting raw Garmin tool output into durable docs, issues, examples, or chats
unless it has been sanitized.
