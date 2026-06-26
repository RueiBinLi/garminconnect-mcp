# Add Garmin Connect MCP to Claude

This server runs locally over stdio. It reads Garmin credentials from this repo's
`.env` file and stores Garmin tokens in `GARMINCONNECT_TOKEN_DIR`, or
`~/.garminconnect` when that variable is not set.

## One-time Garmin login

Run this first from a terminal so MFA prompts are visible:

```bash
cd /path/to/garminconnect-mcp
.venv/bin/garminconnect-mcp login
```

## Claude Code

This repo includes a project-scoped `.mcp.json`:

```json
{
  "mcpServers": {
    "garmin": {
      "type": "stdio",
      "command": "/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp",
      "args": []
    }
  }
}
```

When Claude Code starts in this project, approve the project MCP server if
prompted. Check the connection with:

```bash
claude mcp list
claude mcp get garmin
```

Inside Claude Code, use `/mcp` and test with `garmin_connection_status` or
`garmin_ping`. Do not use `garmin_profile` as a smoke test because it returns
private account data.

To add the same server globally for Claude Code instead of only this project:

```bash
claude mcp add --transport stdio --scope user garmin -- /path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp
```

## Claude Desktop

Use `docs/claude_desktop_config.json` as the config body:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp",
      "args": []
    }
  }
}
```

Typical Claude Desktop config locations:

- Linux: `~/.config/Claude/claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop after updating the file. Then open Connectors or
Developer settings and confirm the `garmin` server is connected.

## Privacy

Garmin responses are private health/account data. Use
`garmin_connection_status` or `garmin_ping` for connection checks, and avoid
pasting raw Garmin tool output into durable docs, issues, examples, or chats
unless it has been sanitized.
