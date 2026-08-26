# Garmin Connect MCP

An [MCP](https://modelcontextprotocol.io) server that exposes your personal Garmin Connect data to MCP-capable clients — Claude Desktop, Claude Code, Codex, and Gemini CLI.

The Garmin work is done by the [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) library; this repo is the thin MCP layer on top: tool definitions, a stdio server, and privacy guardrails that keep raw health payloads out of durable text. Because `python-garminconnect` relies on Garmin Connect's unofficial client behavior, it can break if Garmin changes login or endpoint behavior.

## Setup

```bash
cd /path/to/garminconnect-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
```

For the first login, the safest supported flow is to enter credentials into
temporary shell variables. The password prompt is hidden, and neither value is
written to shell history or a tracked file:

```zsh
read -r "GARMIN_EMAIL?Garmin email: "
read -rs "GARMIN_PASSWORD?Garmin password: "; echo
export GARMIN_EMAIL GARMIN_PASSWORD
.venv/bin/garminconnect-mcp login
unset GARMIN_EMAIL GARMIN_PASSWORD GARMIN_MFA_CODE
```

If Garmin asks for MFA, the login command prompts for the code in the terminal.
Do not send or save the MFA code. The successful login stores reusable tokens in
`~/.garminconnect` by default, outside this repository.

Start a second process to verify that saved-token authentication survives a
restart without credentials:

```bash
.venv/bin/garminconnect-mcp login
```

Both commands are connection-only checks. They do not request private health
payloads and do not create, modify, schedule, or delete Garmin workouts. See
[`docs/MANUAL_TESTING.md`](docs/MANUAL_TESTING.md) for the complete Milestone 1
verification and troubleshooting checklist.

As an alternative, `.env` is ignored by Git and may contain `GARMIN_EMAIL` and
`GARMIN_PASSWORD`, but temporary shell variables reduce the number of credential
copies. Never put credentials or MFA codes in `.env.example`.

## Codex MCP setup

Codex supports local stdio MCP servers in `config.toml`. The ChatGPT desktop app,
Codex CLI, and Codex IDE extension share MCP configuration for the same Codex
host. Register this repository's server at host scope so it appears in desktop
MCP settings (replace the path with this repository's absolute path):

```bash
codex mcp add garmin -- \
  /absolute/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp serve
```

This command stores only the executable path and `serve` argument in the local
Codex host configuration. It does not store Garmin credentials or token values.
Confirm the registration from any directory with `codex mcp get garmin`.

This repository also includes a trusted-project policy configuration at
`.codex/config.toml`. It applies the stricter approval settings below when Codex
is working in this project.

The project configuration starts `.venv/bin/garminconnect-mcp serve`, exposes the
server's complete tool inventory, and prompts before tools by default. Only the
connection-safe `garmin_connection_status` and `garmin_ping` tools are configured
for automatic approval. It contains no credentials or token-directory contents.
The server continues to use saved tokens from `~/.garminconnect` by default,
outside this repository.

After installing the project environment and completing the saved-token login:

1. Register the host-level server with `codex mcp add` as shown above.
2. Open this repository as a trusted Codex project.
3. Fully quit and reopen the ChatGPT desktop app, restart the IDE extension, or
   start a new Codex CLI session. Create a new task so it receives the refreshed
   MCP tool inventory.
4. Use `/mcp` in the composer or Codex terminal UI to confirm that `garmin` is
   enabled and its tools are visible.
5. Ask Codex to run only `garmin_connection_status` (or `garmin_ping`). A
   successful result is `{"ok": true}`.

Do not use profile, activity, health, recovery, or workout tools during this
connection milestone. See [`docs/MANUAL_TESTING.md`](docs/MANUAL_TESTING.md) for
the complete Milestone 2 acceptance checklist and troubleshooting guidance.

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
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall src
```
