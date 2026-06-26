# Garmin Connect MCP

An [MCP](https://modelcontextprotocol.io) server that exposes your personal Garmin Connect data to MCP-capable clients — Claude Desktop, Claude Code, Codex, and Gemini CLI.

The Garmin work is done by the [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) library; this repo is the thin MCP layer on top: tool definitions, a stdio server, and privacy guardrails that keep raw health payloads out of durable text. Because `python-garminconnect` relies on Garmin Connect's unofficial client behavior, it can break if Garmin changes login or endpoint behavior.

## Setup

```bash
cd /path/to/garminconnect-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Edit `.env` with `GARMIN_EMAIL` and `GARMIN_PASSWORD`.

Run once from a terminal to create or refresh saved Garmin tokens:

```bash
.venv/bin/garminconnect-mcp login
```

If Garmin asks for MFA, the login command prompts for the code in the terminal.
For non-interactive use, set `GARMIN_MFA_CODE` temporarily.

The MCP server runs over stdio. Configure Codex with this command:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp"
    }
  }
}
```

Claude config files are included too:

- `.mcp.json` for project-scoped Claude Code use.
- `docs/claude_desktop_config.json` for Claude Desktop.
- `docs/claude.md` for setup and verification steps.

Gemini CLI config files are included too:

- `.gemini/settings.json` for project-scoped Gemini CLI use.
- `docs/gemini_settings.json` for user-scoped Gemini CLI config.
- `docs/gemini.md` for setup and verification steps.

## Tools

Connection-only tools:

- `garmin_connection_status`
- `garmin_ping`

Raw private Garmin data tools:

- `garmin_profile`
- `garmin_daily_stats`
- `garmin_heart_rate`
- `garmin_sleep`
- `garmin_hrv`
- `garmin_body_battery`
- `garmin_stress`
- `garmin_recent_activities`
- `garmin_activity`

Summarized workout tools:

- `garmin_workouts`
- `garmin_scheduled_workouts`
- `garmin_schedule_workout`
- `garmin_create_scheduled_workout`
- `garmin_unschedule_workout`

Dates use `YYYY-MM-DD`. If omitted, tools default to today.

Use `garmin_connection_status` or `garmin_ping` for smoke tests. They validate
login without returning profile, health, or account data.

This is a personal local MCP server, and the raw tools intentionally return full
Garmin payloads. Avoid pasting those raw responses into docs, examples, issues,
or other durable text unless you have sanitized them.

Workout tools return summarized fields instead of raw Garmin payloads. To create
and schedule a new workout, pass Garmin Connect workout JSON to
`garmin_create_scheduled_workout`; to schedule an existing template, use
`garmin_schedule_workout` with its workout ID.

## Development

```bash
scripts/check-private-output.sh
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall src
```
