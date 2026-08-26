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

[`docs/MANUAL_TESTING.md`](docs/MANUAL_TESTING.md) records the completed,
read-only Milestone 5 running-summary acceptance checklist and its privacy
boundary.

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

Raw private Garmin profile tool:

- `garmin_profile`

Normalized read-only recovery tools:

- `garmin_daily_stats`
- `garmin_heart_rate`
- `garmin_sleep`
- `garmin_hrv`
- `garmin_hrv_range(start_date, end_date)`
- `garmin_body_battery`
- `garmin_stress`

Normalized read-only activity tools:

- `garmin_recent_activities(start=0, limit=10, running_only=false)`
- `garmin_activity(activity_id)`
- `garmin_running_activities_by_date(start_date, end_date)`
- `garmin_weekly_running_summary(start_date, end_date)`
- `garmin_compare_running_weeks(current_week_start, previous_week_start)`
- `garmin_compare_recent_long_runs(end_date, limit=3)`

Normalized read-only workout tools:

- `garmin_workouts(start=0, limit=20, running_only=false)`
- `garmin_scheduled_workouts(start_date, end_date)`

Legacy workout write tools (not part of Milestone 6):

- `garmin_schedule_workout`
- `garmin_create_scheduled_workout`
- `garmin_unschedule_workout`

Dates use strict `YYYY-MM-DD` formatting. Single-date recovery tools default to
today when the date is omitted. HRV ranges are inclusive and limited to 14 days.

Use `garmin_connection_status` or `garmin_ping` for smoke tests. They validate
login without returning profile, health, or account data.

The activity list supports offsets from zero and page sizes from 1 through 100.
Set `running_only=true` to request running activities. Both activity tools return
the same compact fields: activity ID, local and GMT start times, type, name,
distance in meters, duration in seconds, pace in seconds per kilometer, heart
rate in bpm, cadence in spm, and elevation gain in meters. Garmin fields that are
not present are returned as `null`; the server does not estimate missing values.
Pace is present only when Garmin supplies average speed, which is converted from
meters per second to seconds per kilometer.

Activity responses are normalized behind a Garmin provider boundary and never
return raw chart, polyline, owner, profile-image, role, or privacy metadata.
Invalid pagination, unknown IDs, malformed responses, authentication failures,
rate limits, and endpoint failures produce bounded, secret-safe errors.

Milestone 5 date ranges are inclusive, require strict `YYYY-MM-DD`, and contain
at most 42 days. Retrieval uses Garmin's running-filtered date endpoint, which
handles pagination inside the existing Garmin dependency, then verifies the
normalized activity type at the provider boundary. The tools never request
profiles, recovery, workouts, schedules, or training plans.

Weekly summaries use Monday through Sunday calendar weeks and include clipped
range boundaries for partial first or last weeks. They return running activity
count, distance in meters, duration in seconds, the range's longest measured-
distance run, and each week's longest measured-distance run. Activities without
a usable local or GMT start date remain visible in unassigned coverage counts
but are not silently placed in a week.

Known measurements are summed even when other activities lack the field, with
available/unavailable counts and a completeness flag beside each total. If all
activities in a non-empty week lack distance or duration, that total is `null`;
an empty week has a factual zero total. Missing values are never treated as
zero. Week-over-week changes are absolute meter/second/count differences, and
completeness flags expose partial comparisons.

For recent long-run comparison, the deterministic rule is the greatest supplied
`distance_m` in each Monday-Sunday week. The bounded query covers the week
containing the end date plus the requested one to four preceding calendar weeks
(at most 35 inclusive days). The most recent available weekly candidate is
compared with the preceding candidates. Weeks without a supplied distance have
no candidate, duration changes remain `null` if unavailable, and the output
contains facts only—not session labels, coaching recommendations, or medical
interpretation.

Recovery tools return compact factual measurements only. Daily statistics use
meters, seconds, kcal, and bpm. Heart-rate summaries use bpm; sleep and sleep
stages use seconds; HRV uses milliseconds; Body Battery and stress retain
Garmin's native scales. Sleep timestamps are normalized to UTC ISO 8601. Garmin
score/status labels are passed through without interpretation. Missing fields
are returned as `null`, missing HRV range days are omitted, and no value is
estimated.

The recovery provider discards per-sample heart-rate, movement, respiration,
HRV, Body Battery, and stress arrays after deriving the documented daily
summary. Invalid dates and ranges, malformed responses, authentication failures,
rate limits, and endpoint failures produce bounded, secret-safe errors. These
tools are read-only and cannot affect a Garmin watch.

The profile tool still returns a raw private Garmin payload. Avoid using it for
verification or pasting its response into durable text.

The two workout read tools route through a dedicated provider and pure
normalizers. Saved templates accept a zero-based public offset and a page size
from 1 through 100. The provider translates this to Garmin's current one-based
“My Workouts” query with `myWorkoutsOnly=true`, excluding service entries the UI
does not render. `running_only=true` uses Garmin's `sportTypeKey=running` query
and is checked again after normalization. `source_count` reports the fetched
filtered page size and `count` reports items remaining after the defensive
check. Pagination values require JSON integers and `running_only` requires a
JSON Boolean; coercible strings and numbers are rejected at the MCP boundary.
Results follow Garmin's updated-date-descending UI order.

Scheduled ranges are strict, inclusive `YYYY-MM-DD` ranges of at most 31 days.
Garmin exposes calendar months, so the provider fetches only intersecting
months, immediately discards non-workout calendar items, filters to the requested
range, and orders by scheduled date and identifiers. `scheduled_date` is a
Garmin calendar date, not a timestamp; the server does not infer a timezone or
instant.

Both read tools return only workout/schedule IDs, name, sport type, description,
estimated duration in seconds, estimated distance in meters, and scheduled date
where applicable. Every absent declared field is `null`. Owner/account metadata,
internal URLs, arbitrary identifiers, and detailed steps are discarded. Empty
pages and ranges return zero counts and empty items. Invalid inputs, malformed
known envelopes, authentication failures, rate limits, and endpoint failures
produce bounded secret-safe errors.

The legacy write tools are unchanged and remain outside Milestone 6. Do not use
them during read-only workout verification.

## Development

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall src
```
