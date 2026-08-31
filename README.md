# Garmin Connect MCP

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server
that lets Codex work with your Garmin Connect data.

Use natural-language prompts to review training and recovery, compare running
weeks, inspect workouts, build structured running sessions, and—only after
explicit confirmation—schedule workouts in Garmin Connect.

The server uses
[`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect),
normalizes Garmin responses into compact schemas with explicit units, and runs
locally over stdio. It is built and verified with Codex. Because it uses the
standard MCP transport, it should also be compatible with other stdio MCP
clients, but those clients have not been verified by this project.

Garmin Connect does not provide an official public API for this use case, so
authentication or endpoints may occasionally change.

## What it can do

### Read training and recovery data

- List recent activities or runs within a date range.
- Inspect activity distance, duration, pace, heart rate, cadence, elevation,
  laps, recorded temperature, and associated historical weather.
- Calculate factual aerobic-drift metrics for a run without returning the raw
  sample stream.
- Read daily statistics, heart rate, sleep, HRV, Body Battery, and stress.
- Read configured running heart-rate zones.
- List saved workouts and scheduled workouts.

### Analyze running

- Summarize distance, duration, frequency, and longest run by calendar week.
- Compare adjacent running weeks.
- Compare recent weekly long runs.
- Produce a transparent Monday-to-Sunday running proposal from recent training,
  recovery, available dates, existing calendar commitments, and configured
  heart-rate zones.

The analysis separates Garmin measurements from interpretation. Missing values
remain unavailable instead of being estimated or silently treated as zero.

### Create and schedule running workouts

- Validate and preview structured workouts entirely offline.
- Create one reviewed running workout without scheduling it.
- Preview and schedule an existing workout on a specific date.
- Create and schedule one new workout in a guarded operation.
- Preview a weekly plan, review its exact fingerprint, and schedule only that
  approved plan.
- Remove a calendar assignment without deleting its workout template.

Write tools default to preview/no-write behavior or require
`confirmed=true`. The server does not silently overwrite, reschedule, or delete
workout templates.

## Requirements

- Python 3.12 or newer
- A Garmin Connect account
- Codex desktop, CLI, or IDE extension with MCP support

## Install

From a local checkout of this repository:

```bash
cd /path/to/garminconnect-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Install the development tools too if you plan to run tests or contribute:

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

## Sign in to Garmin Connect

The recommended first-login flow keeps credentials out of tracked files and
shell history:

```zsh
cd /path/to/garminconnect-mcp
read -r "GARMIN_EMAIL?Garmin email: "
read -rs "GARMIN_PASSWORD?Garmin password: "; echo
export GARMIN_EMAIL GARMIN_PASSWORD
.venv/bin/garminconnect-mcp login
unset GARMIN_EMAIL GARMIN_PASSWORD GARMIN_MFA_CODE
```

If Garmin requests MFA, enter the code at the terminal prompt. A successful
login stores reusable tokens in `~/.garminconnect` by default. Verify that the
saved session works without credentials:

```bash
.venv/bin/garminconnect-mcp login
```

You can change the token location with `GARMINCONNECT_TOKEN_DIR`. An ignored
`.env` file is also supported—copy `.env.example` to `.env` and fill it in—but
temporary shell variables leave fewer credential copies behind.

Never commit Garmin credentials, MFA codes, session tokens, or raw health data.

## Connect to Codex

Register the server for the current Codex host using the absolute path to its
executable:

```bash
codex mcp add garmin -- \
  /absolute/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp serve
codex mcp get garmin
```

This repository also includes a project-scoped `.codex/config.toml`. After
installation and login:

1. Open the repository as a trusted Codex project.
2. Fully restart the Codex app, CLI, or IDE extension so it reloads the MCP tool
   inventory.
3. Start a new task and use `/mcp` to confirm that `garmin` is enabled.
4. Ask Codex to check the Garmin connection without reading personal data.

Codex should call `garmin_connection_status` or `garmin_ping` and receive
`{"ok": true}`. Avoid using `garmin_profile` as a smoke test because it returns
raw private profile data.

## Using other MCP clients

The server itself is not tied to Codex. Any MCP client that can launch a local
stdio server can use this command:

```bash
/absolute/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp serve
```

Example configuration files for Claude and Gemini are included in `.mcp.json`,
`.gemini/settings.json`, and `docs/`. They are provided as starting points and
may need adjustment for the client's current configuration format. This project
does not currently claim verified support for those clients.

## Example prompts

You normally do not need to name a tool. Describe the result you want and state
clearly whether the task must remain read-only.

### Review recent training

> Summarize my running over the last four complete Monday-to-Sunday weeks.
> Compare weekly distance, run count, duration, and longest run. Clearly separate
> Garmin facts from your interpretation, and flag incomplete data.

> Compare my last three weekly long runs. Include distance, duration, average
> pace, and average heart rate where available. Do not estimate missing values.

> Analyze aerobic drift for my most recent easy run. First explain whether the
> activity is usable for this calculation, then summarize the factual result in
> plain language.

### Review recovery

> Show my sleep, HRV, resting heart rate, Body Battery, and stress for the last
> seven days. Summarize trends, but do not give medical advice.

> Compare today's recovery data with the previous seven days and tell me which
> measurements are unavailable.

### Inspect workouts and calendar

> List my running workout templates and the workouts scheduled for the next two
> weeks. This is read-only; do not change Garmin Connect.

`garmin_scheduled_workouts(start_date, end_date)` reads past or future scheduled
workouts for an inclusive range of up to 31 days, including across month/year
boundaries. It supports both flat Garmin calendar workout entries and embedded
workout records. Saved templates without a calendar assignment are not included.
Only workouts exposed by Garmin's calendar endpoint are visible. Missing
estimates remain `null`; generic calendar duration/distance units are not assumed.
After updating the server, reconnect the Garmin MCP or restart its client to load
the calendar parsing fix. No configuration or dependency changes are required.

### Build a workout safely

> Preview—but do not create—a running workout named “Easy 45” with a 10-minute
> warmup, 30 minutes in my configured Zone 2, and a 5-minute cooldown. Show the
> expanded steps and total duration.

After reviewing the preview, make the intent explicit in a separate prompt:

> Create exactly the reviewed “Easy 45” workout, but do not schedule it. Use the
> confirmation-safe creation tool with explicit confirmation.

### Schedule an existing workout safely

> Preview scheduling workout ID 123456789 on 2026-09-05. Do not write anything.

After reviewing the exact ID and date:

> Schedule that exact workout on that exact date with explicit confirmation. Do
> not create, modify, or delete any other workout.

### Propose and approve a week

> Propose a half-marathon training week beginning 2026-09-07. I can run Tuesday,
> Thursday, and Sunday; prefer Sunday for the long run; allow at most three
> sessions. Preserve anything already scheduled and do not write to Garmin.

To schedule a proposal, first request its approval-bound preview. Review every
session, date, workout step, warning, and the proposal fingerprint. Then approve
that exact fingerprint in a separate prompt before the approval token expires.
Weekly scheduling is sequential rather than transactional; if a later write
fails, earlier successful sessions remain in Garmin Connect.

## Recommended tool workflows

When selecting tools directly, prefer these guarded sequences:

| Goal | Preview/read tool | Confirmed write tool |
| --- | --- | --- |
| Create a workout | `garmin_preview_running_workout` | `garmin_create_running_workout` |
| Schedule an existing workout | `garmin_preview_workout_schedule` | `garmin_schedule_existing_workout` |
| Create and schedule | `garmin_preview_create_and_schedule_running_workout` | `garmin_create_and_schedule_running_workout` |
| Plan and schedule a week | `garmin_preview_weekly_running_plan` | `garmin_schedule_weekly_running_plan` |
| Remove a calendar assignment | `garmin_unschedule_existing_workout` without confirmation | The same tool with `confirmed=true` |

Dates use strict `YYYY-MM-DD` formatting. Weekly planning uses a Monday
`week_start`. The current deterministic weekly planner supports the
`half_marathon` plan type and uses configured running Zone 2 heart-rate bounds.

The older `garmin_schedule_workout`, `garmin_create_scheduled_workout`, and
`garmin_unschedule_workout` tools remain for compatibility. New integrations
should use the guarded tools above.

## Available tools

Connection and account:

- `garmin_connection_status`
- `garmin_ping`
- `garmin_profile` (raw private data)

Recovery and physiology:

- `garmin_daily_stats`
- `garmin_heart_rate`
- `garmin_sleep`
- `garmin_hrv`
- `garmin_hrv_range`
- `garmin_body_battery`
- `garmin_stress`
- `garmin_running_heart_rate_zones`

Activities and analysis:

- `garmin_recent_activities`
- `garmin_activity`
- `garmin_activity_temperature`
- `garmin_activity_weather`
- `garmin_activity_splits`
- `garmin_activity_aerobic_drift`
- `garmin_running_activities_by_date`
- `garmin_weekly_running_summary`
- `garmin_compare_running_weeks`
- `garmin_compare_recent_long_runs`
- `garmin_weekly_running_proposal`

Workouts and scheduling:

- `garmin_workouts`
- `garmin_scheduled_workouts`
- `garmin_preview_running_workout`
- `garmin_create_running_workout`
- `garmin_preview_workout_schedule`
- `garmin_schedule_existing_workout`
- `garmin_unschedule_existing_workout`
- `garmin_preview_create_and_schedule_running_workout`
- `garmin_create_and_schedule_running_workout`
- `garmin_preview_weekly_running_plan`
- `garmin_schedule_weekly_running_plan`

## Privacy and safety

- The server runs locally and communicates with Codex over stdio.
- Most responses are normalized and omit raw sample arrays, account metadata,
  coordinates, URLs, and other unnecessary private fields.
- `garmin_profile` is intentionally raw and should be used sparingly.
- Health and training output is informational, not medical advice.
- Read operations may run automatically; Garmin writes should always follow an
  exact preview and explicit user approval.
- Workout creation has no stable Garmin idempotency key. If a create request has
  an uncertain outcome, inspect Garmin Connect before trying again to avoid a
  duplicate.
- Garmin may synchronize scheduled calendar items to connected devices on its
  own; this server does not directly push workouts to a watch.

For deeper implementation details, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). For opt-in manual Garmin checks
and troubleshooting, see [`docs/MANUAL_TESTING.md`](docs/MANUAL_TESTING.md).

## Development

The default test suite uses synthetic data and does not contact a real Garmin
account or perform Garmin writes.

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall src
```

## License

[MIT](LICENSE)
