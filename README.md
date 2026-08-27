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
offline-only Milestone 7 workout-preview acceptance checklist and its privacy
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
- `garmin_weekly_running_proposal(week_start, constraints)`

Normalized read-only workout tools:

- `garmin_workouts(start=0, limit=20, running_only=false)`
- `garmin_scheduled_workouts(start_date, end_date)`

Weekly plan approval tools (Milestone 12 complete):

- `garmin_preview_weekly_running_plan(week_start, constraints)`
- `garmin_schedule_weekly_running_plan(approval_token, proposal_fingerprint, confirmed=false)`

Offline pre-write workout tool:

- `garmin_preview_running_workout(definition)`

Validated workout-creation tool:

- `garmin_create_running_workout(definition, confirmed=false)`

Safe existing-workout calendar tools (Milestone 9 complete):

- `garmin_preview_workout_schedule(workout_id, scheduled_date)`
- `garmin_schedule_existing_workout(workout_id, scheduled_date, confirmed=false)`
- `garmin_unschedule_existing_workout(scheduled_workout_id, confirmed=false)`

Safe combined creation and scheduling tools (Milestone 10 complete):

- `garmin_preview_create_and_schedule_running_workout(definition, scheduled_date)`
- `garmin_create_and_schedule_running_workout(definition, scheduled_date, confirmed=false)`

Legacy workout write tools (behavior preserved; do not use for Milestones 9–10):

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

Milestone 7 adds a strict internal running-workout definition and an offline
preview. A definition fixes `sport_type` to `running`, accepts a conservatively
validated name and optional description, and contains ordered `warmup`, `run`,
`recovery`, `cooldown`, or bounded `repeat` steps. Executable steps require
exactly one time (`duration_s`), distance (`distance_m`), or open duration.
Targets are optional and limited to no target, a custom heart-rate range in
`heart_rate_bpm`, or a custom pace range in `pace_s_per_km`. Unknown fields,
coercible strings, Booleans used as numbers, invalid ranges, non-finite values,
unsupported combinations, unsafe nesting, and excessive expanded totals are
rejected.

The preview expands repeats into readable execution order and reports known and
complete totals separately. A complete duration or distance total is `null`
when another duration type makes that total indeterminate; the known subtotal
and a completeness Boolean remain visible. The tool clearly reports
`uploaded=false` and `scheduled=false`. It does not construct the Garmin client,
make a network call, expose the Garmin payload, or reach any upload, create,
schedule, modify, unschedule, or delete operation.

Garmin enum IDs and payload keys live only in the dedicated serializer. The
serializer is offline and internally testable for the installed client's
verified running, step, end-condition, repeat, heart-rate, and pace mappings.
Pace seconds per kilometer are converted to Garmin's wire speed only inside
that boundary. The serializer is not connected to a write tool.

The legacy write tools are unchanged and remain outside Milestone 7. Do not use
them during workout-preview verification.

Milestone 8 connects the same strict `WorkoutDefinition` and deterministic
serializer to one narrow creation boundary. `confirmed` is a strict JSON
Boolean and defaults to `false`. An omitted or false confirmation validates the
complete definition, constructs no Garmin client, performs no network request,
and returns a compact reminder to use the existing preview before explicitly
confirming. Arbitrary Garmin JSON, arrays, enum IDs, and unknown fields are not
accepted by this tool.

A confirmed invocation serializes the validated definition once and calls the
installed client's workout upload method exactly once. It does not retry after
an uncertain result and has no scheduling, modification, unscheduling,
deletion, calendar, or device-push path. The response retains only `created`,
`workout_id`, the validated name and running sport, complete duration/distance
totals where determinable, `scheduled=false`, and a clear unscheduled message.
Garmin response names, owner/account metadata, URLs, raw payloads, and unrelated
identifiers are discarded. Authentication expiration, rate limits, endpoint
failures, unsupported client behavior, malformed responses, and missing workout
IDs become concise secret-safe errors.

Milestone 8 was completed and manually verified on 2026-08-27 with exactly one
explicitly approved synthetic creation. The workout was created successfully,
opened normally, retained the intended running step order and durations, and
remained unscheduled; no duplicate, calendar change, or device push occurred.
Every future creation still requires a separately reviewed definition and
explicit confirmation. See [`docs/MANUAL_TESTING.md`](docs/MANUAL_TESTING.md).

Milestone 9 adds a separate safe boundary for one existing workout and one
Garmin calendar date. IDs must be positive ASCII decimal strings, dates must be
exact `YYYY-MM-DD` calendar labels, confirmation must be a JSON Boolean, and
unknown top-level fields are rejected. Preview and omitted/false scheduling
confirmation are fully offline: they validate the complete request without
constructing a Garmin client or changing Garmin.

A confirmed schedule performs one normalized read-only check for an exact
workout/date duplicate. An existing assignment returns a compact idempotent
result without another schedule call. Otherwise, scheduling is invoked once and
returns only schedule state, the assignment ID, requested workout ID/date, and a
status message. It never creates, uploads, modifies, deletes, or clones a
workout, and it never calls Garmin's device-push method. Garmin may independently
synchronize calendar state to connected devices.

Unscheduling has a separate confirmation. Its default path reads one assignment
by scheduled-workout ID and shows only its normalized ID, workout ID, and
calendar date without writing. A confirmed call repeats that read immediately,
then invokes unscheduling once. It removes only the calendar assignment and
returns `workout_deleted=false`; no template deletion, retry, rollback, or
automatic cleanup is performed.

The installed `garminconnect 0.3.11` schedule wrappers do not use its transient
retry decorator, but the low-level client normally replays once after an HTTP
401. The provider temporarily blocks authentication refresh during only these
two writes, after the preceding read has safely refreshed expiring credentials.
A write-time authentication failure therefore stops before a second HTTP
attempt. Network/endpoint ambiguity, malformed responses, and missing schedule
IDs are reported as uncertain and must be inspected manually before any retry.

Milestone 9 was completed and manually verified on 2026-08-27. One existing test
workout was scheduled only after exact approval, verified in Garmin Connect,
then removed only after a second exact approval. The template remained intact,
no duplicate or unrelated calendar change occurred, and no device-push method
was called. Private assignment values are intentionally absent from this record.
See [`docs/MANUAL_TESTING.md`](docs/MANUAL_TESTING.md).

Milestone 10 composes the strict creation and duplicate-aware scheduling
boundaries for exactly one new workout and one calendar date. Its preview and
false/omitted confirmation paths are fully offline and expose only the normalized
definition, expanded execution order, aggregates, date, no-write state, and
device-synchronization warning. Arrays, raw Garmin JSON, pre-existing workout
IDs, timestamps, coercible values, and unknown fields are rejected before client
construction.

A confirmed call performs one guarded upload, validates one returned workout ID,
then uses only that ID for the existing normalized exact-duplicate read and at
most one guarded scheduling call. Upload and schedule both block the pinned
dependency's HTTP-401 replay path. No automatic retry, rollback, cleanup,
unscheduling, deletion, modification, cloning, or direct device push is present.
If scheduling fails after creation, the compact result reports
`partial_failure=true` and preserves the new unscheduled workout.

Garmin provides no stable idempotency key for workout creation and this project
has no database, so duplicate creation cannot be guaranteed after an uncertain
upload. Never retry an uncertain creation. Inspect Garmin Connect manually before
proposing any further action.

Milestone 10 was completed and manually verified on 2026-08-27. After the first
approved invocation stopped on expired authentication, manual inspection found
no created test workout. The saved login was refreshed, the exact proposal was
approved again, and one new synthetic running workout was created and scheduled
successfully on the approved date. Manual verification confirmed the template,
steps, assignment, lack of duplicates, unchanged existing workouts/calendar
items, and normal device synchronization behavior. No private IDs or raw Garmin
data are retained. The test workout was not automatically unscheduled or deleted.

## Milestone 11 weekly running proposals

Milestone 11 was completed and manually verified read-only on 2026-08-27. No
Garmin workout or calendar change was made and no private value was retained.

`garmin_weekly_running_proposal(week_start, constraints)` produces one compact,
read-only Monday-Sunday proposal. `week_start` must be a strict `YYYY-MM-DD`
Monday. The strict constraints object accepts only:

- `plan_type`: currently exactly `half_marathon`, rendered as `HM`;
- `plan_start_date`: a strict Monday; its week is `W01`;
- `available_dates`: one to seven unique dates inside the proposal week;
- `desired_sessions`: requested session count from 1 through 7;
- `maximum_sessions`: integer from 1 through 7 (default 3);
- `preferred_long_run_date`: an available date inside the week;
- `maximum_weekly_distance_m`: 1,000 through 300,000 meters;
- `user_note`: 1 through 200 printable ASCII characters.

The proposal week must not precede `plan_start_date`. Workout names use the
deterministic format `{code} W{week} - {purpose} {distance}`, with a two-digit
week and total workout distance in kilometers. Examples include
`HM W05 - Easy 8K` and `HM W05 - Long 16K`; fractional totals remain explicit,
such as `HM W05 - Easy 7.5K`.

The bounded reads are the 28 days immediately before the proposal week for
normalized running activities, the final 7 of those days for normalized HRV,
and the requested 7-day week for normalized scheduled workouts. Existing
scheduled runs are preserved as commitments and consume both their date and
session capacity. IDs, descriptions, raw calendar objects, and Garmin payloads
are discarded from the proposal.

One additional read retrieves configured heart-rate-zone floors. The running
profile is preferred; Garmin's default profile is used only when running zones
are absent, and `source_sport` exposes that fallback. Only normalized bpm
ranges, the training method, and compact heart-rate facts survive. Raw
biometric settings, profile/account fields, and device data are discarded.

The initial product policy is deliberately simple. At least two non-empty
lookback weeks must have complete distance coverage. Their median weekly
distance, rounded to 100 m, is the distance baseline; the floor of their median
run count is the session baseline. Two or more Garmin HRV statuses equal to
`low`, `unbalanced`, or `poor` apply an explicit 0.90 distance multiplier. The
optional distance cap is then applied. The long run receives 100% with one new
session, 60% with two, or 40% with three or more; the remainder is divided
equally. Each proposal uses a strict
distance-based `WorkoutDefinition` with 10% untargeted warmup, an 80% main step
targeted to Garmin's exact configured Zone 2 bpm bounds, and 10% untargeted
cooldown. `desired_sessions` replaces the historical session baseline when
supplied, while `maximum_sessions` remains a hard cap. These are transparent
product rules, not scientific guarantees or medical conclusions.

Insufficient history returns no new sessions instead of invented precision.
Missing measurements remain unavailable rather than zero. The response keeps
facts, coverage, constraints, rules/calculations, warnings, commitments,
proposed sessions, and aggregates separate, and always reports
`proposal_only=true`, `created=false`, and `scheduled=false`. This workflow has
no create, upload, schedule, modify, unschedule, delete, retry, cleanup, or
device-push path.

## Milestone 12 weekly plan approval and scheduling

Milestone 12 was completed and manually verified on 2026-08-27. After the full
offline gate passed, one fresh read-only proposal received explicit approval of
its exact fingerprint and was invoked once. The user confirmed that every
workout and calendar assignment matched, no duplicates existed, existing items
were preserved, and no unrelated change occurred. No private live value is
retained in this repository.

`garmin_preview_weekly_running_plan` reuses the exact Milestone 11 request model,
normalized facts, configured running Zone 2, scheduled commitments, deterministic
policy, and strict WorkoutDefinitions. The response adds the exact ordered list
of intended creations and schedules, a deterministic `sha256:` proposal
fingerprint, and an opaque approval token. The fingerprint covers all reviewed
facts, coverage, constraints, commitments, rules, calculations, warnings,
unavailable inputs, dates, purposes, definitions, steps, targets, units,
aggregates, and intended writes. Identical input produces an identical
fingerprint. The token is process-local, expires after 15 minutes, is bounded in
memory, and is valid for one confirmed invocation. Restarting the server loses
pending approvals.

The scheduling tool accepts only the opaque token, exact fingerprint, and a
strict JSON Boolean `confirmed`. It never accepts a proposal, Garmin JSON,
calendar object, workout ID, scheduled-workout ID, account value, device value,
URL, or serialized payload. False or omitted confirmation is fully offline and
does not consume the approval. True confirmation consumes it before execution,
revalidates every cached definition and aggregate, then rereads only the
normalized Monday-Sunday calendar. Any calendar change makes the approval stale;
a newly added commitment on a proposed date is reported as a conflict. Both stop
before all writes and require a fresh preview. Dates are never moved silently.

Sessions execute in ascending approved date and `execution_order`. For each
session, the existing safe provider serializes and uploads exactly one new
workout, performs its duplicate read, and schedules only the newly returned ID
on the approved date. Processing stops immediately after a known or uncertain
failure. Successful earlier sessions and a newly created unscheduled workout
are preserved; later sessions are marked not attempted. There is no retry,
rollback, cleanup, deletion, modification, unscheduling, cloning, legacy write,
or device-push path.

Garmin supplies no stable idempotency key for workout creation. The weekly
operation is sequential, not transactionally atomic, and cannot guarantee
duplicate prevention after an uncertain creation response. Never replay a used
approval or retry an uncertain outcome. Inspect Garmin Connect manually and
generate a new preview before any later action. Public outcomes omit workout and
schedule identifiers, raw requests/responses, endpoint details, upstream text,
account/profile fields, URLs, tokens, calendar payloads, and device identifiers.

## Development

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall src
```
