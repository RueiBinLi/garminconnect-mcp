# Garmin Connect MCP — Architecture and Upstream Audit

## Milestone history and current scope

This document records the repository as audited on 2026-08-25. Milestone 0
changes documentation only; it does not add or change MCP behavior.

Milestone 3 introduced the first Garmin provider/normalization boundary for
read-only activities. Milestone 4 extended that boundary to recovery data and
was manually verified. Milestone 5 adds deterministic running aggregation over
normalized activities and was manually verified on 2026-08-26.

## Repository structure

```text
garminconnect-mcp/
├── src/garminconnect_mcp/server.py  # Authentication, MCP tools, CLI
├── src/garminconnect_mcp/provider.py # Garmin activity/recovery providers and safe errors
├── src/garminconnect_mcp/activities.py # Pure activity normalization and schema
├── src/garminconnect_mcp/training.py # Pure weekly and long-run aggregation
├── src/garminconnect_mcp/recovery.py # Pure recovery normalization and schemas
├── tests/test_server.py             # Synthetic unit tests with a fake Garmin client
├── tests/test_provider.py           # Synthetic activity provider/error tests
├── tests/test_activities.py         # Synthetic activity normalization tests
├── tests/test_training.py           # Synthetic running aggregation tests
├── tests/test_recovery.py           # Synthetic recovery normalization tests
├── tests/test_recovery_provider.py  # Synthetic recovery provider/error tests
├── tests/test_private_output_scanner.py
├── scripts/check-private-output.sh  # Durable-text privacy scanner
├── docs/                            # Client setup, specification, and roadmap
├── pyproject.toml                   # Package metadata and dependencies
├── .env.example                     # Local credential configuration template
└── .gitignore                       # Local secret/build/cache exclusions
```

The implementation remains intentionally small. Activity and recovery behavior
have provider seams and pure normalizers; other runtime behavior still lives in
`server.py`. `training.py` performs factual aggregation only; there is no
coaching or planning module.

## Current activity architecture

```text
MCP client
    │ stdio
    ▼
FastMCP activity tools (`server.py`)
    │ bounded request parameters and stable tool responses
    ▼
Garmin activity provider (`provider.py`)
    │ endpoint selection and secret-safe error mapping
    ▼
Cached `garminconnect.Garmin` client
    │ unofficial Garmin Connect behavior
    ▼
Garmin Connect

Garmin response
    │ explicit supported envelopes and fields only
    ▼
Pure activity normalizer (`activities.py`)
    │ compact schema with explicit units and null unavailable values
    ▼
FastMCP activity response
```

`FastMCP("Garmin Connect")` still supplies the framework and the console entry
point remains `garminconnect-mcp = garminconnect_mcp.server:main`. With no
command, or with `serve`, `main()` calls `mcp.run()` over stdio. Authentication,
token reuse, and stdio startup are unchanged.

Activity and recovery MCP tools no longer depend on Garmin response keys or
exception text. Other tool families still call the third-party client directly
and should move behind equivalent boundaries only in their own milestones.

## Activity response boundary

The upstream recent-activity response was verified live with only five items,
and one recent run was selected for a single-activity shape check. Nothing was
written to Garmin, and no raw payload was saved. The observed five-item raw list
was about 20 KB and a representative item contained 81 fields, including many
fields irrelevant to training summaries. The chart/polyline-oriented detail
response was about 8 KB even with minimal chart/polyline limits.

The activity provider therefore uses the compact activity summary endpoint for
single-activity lookup. The normalizer discards all fields except the stable
contract below:

| Field | Type/unit | Unavailable behavior |
| --- | --- | --- |
| `activity_id` | string identifier | `null` |
| `start_time_local` | Garmin local date/time string | `null` |
| `start_time_gmt` | Garmin GMT date/time string | `null` |
| `activity_type` | Garmin type key | `null` |
| `name` | string | `null` |
| `distance_m` | meters | `null` |
| `duration_s` | seconds | `null` |
| `pace_s_per_km` | seconds per kilometer | `null` |
| `average_heart_rate_bpm` | beats per minute | `null` |
| `maximum_heart_rate_bpm` | beats per minute | `null` |
| `average_cadence_spm` | steps per minute | `null` |
| `elevation_gain_m` | meters | `null` |

Pace is a unit conversion from Garmin's supplied average speed. It remains
`null` if that field is absent or invalid; distance and duration are not used to
estimate it. The normalizer uses explicit known top-level/summary envelopes and
rejects unrecognized shapes rather than recursively searching arbitrary Garmin
payloads.

Recent retrieval accepts offsets from zero and page sizes from 1 through 100.
Running-only requests are filtered at Garmin's endpoint and checked again at the
normalization boundary. Stable provider errors distinguish invalid requests,
authentication failures, unknown activities, malformed responses, rate limits,
and general endpoint failures without copying upstream exception text.

## Milestone 5 running-summary boundary

The provider exposes one new read-only operation over the dependency's
`get_activities_by_date` method. It validates strict inclusive dates, limits the
range to 42 days, requests only running activities in ascending order, and
normalizes every returned item before a second running-type check. The existing
dependency performs endpoint pagination. No profile, recovery, workout,
schedule, training-plan, write, or delete method participates in this flow.

```text
Four narrow MCP summary tools
    │ strict dates and small limits
    ▼
GarminActivityProvider.running_activities_by_date
    │ running-filtered, inclusive, maximum 42-day endpoint request
    ▼
Existing activity normalizer
    │ canonical meter/second schema and null unavailable fields
    ▼
Pure training aggregation
    │ Monday-Sunday bins, coverage, longest-distance facts, deltas
    ▼
Compact factual MCP response
```

Weekly aggregation prefers the normalized local start date and falls back to
the normalized GMT start date. An activity with neither a usable date is counted
as unassigned rather than silently dropped into a week. Each distance and
duration total reports available and unavailable activity counts plus a
completeness flag. A non-empty group with no supplied measurement returns
`null`; a partially covered group returns the sum of known measurements with
`complete=false`; an empty week returns zero with complete empty coverage.

The longest run is the activity with the greatest supplied `distance_m`, with
earliest start time and then activity ID as deterministic tie breakers. Recent
long-run comparison applies this rule once per Monday-Sunday week. Its query
covers the end date's week plus one to four preceding calendar weeks, for at
most 35 inclusive days, and compares the newest available candidate with the
preceding candidates. This is the only long-run classification rule. The module
does not classify effort, estimate metrics, interpret health data, or recommend
training.

## Recovery response boundary

Milestone 4 made one read-only structural call for each daily recovery endpoint,
plus one three-day HRV-range call. The probe reported only encoded byte counts,
container types, field names, and collection lengths; raw payloads and values
were neither displayed nor saved. The largest response was sleep at about 96 KB,
while heart-rate and stress responses contained hundreds of chart samples. The
single-date HRV response also contained nightly samples; the range endpoint
returned compact daily summaries. No unrelated Garmin endpoint or write/delete
operation was invoked.

The recovery tools route through `GarminRecoveryProvider`, which validates dates,
selects only read endpoints, maps upstream failures to secret-safe categories,
and passes responses to pure functions in `recovery.py`. The normalizers retain
only these factual contracts:

| Schema | Compact fields and units |
| --- | --- |
| Daily statistics | requested date; step counts; distance in meters; energy in kcal; activity, sedentary, sleep, and intensity durations in seconds; heart rate in bpm; Garmin-native stress and Body Battery summaries |
| Heart rate | requested date; resting, minimum, maximum, and seven-day average resting heart rate in bpm |
| Sleep | requested date; UTC ISO 8601 start/end times; total, stage, awake, unmeasurable, and nap durations in seconds; Garmin sleep score and status labels |
| HRV | date; weekly average, last-night average, and last-night five-minute high in milliseconds; Garmin status |
| Body Battery | requested date; charged, drained, highest, lowest, and latest values on Garmin's native scale |
| Stress | requested date; average and maximum values on Garmin's native scale |

Every declared measurement remains present as `null` when Garmin does not supply
it. The server never estimates absent values and does not add interpretation or
medical advice. Per-sample chart, movement, respiration, HRV, Body Battery,
stress, event, profile, and identifier data is discarded. Body Battery high,
low, and latest values are reductions over Garmin-supplied native samples, not
estimated measurements.

All recovery dates use strict `YYYY-MM-DD` validation before a Garmin client is
created. HRV range dates are inclusive, ordered, and limited to 14 days. The
upstream range endpoint may omit days without summaries; present summaries still
contain every normalized key with null unavailable fields.

## Codex integration

Milestone 2 registers the server in the local Codex host configuration and adds
a trusted-project policy configuration in `.codex/config.toml`. Both use Codex's
supported stdio MCP transport to start the existing console entry point with
`serve`:

```text
Codex host
    │ host config registers the repository's absolute executable path
    │ project config applies stricter tool approval policy
    │ starts garminconnect-mcp serve
    ▼
FastMCP stdio server
    │ lists 21 MCP tools without contacting Garmin
    │ invokes only an explicitly selected tool
    ▼
Saved-token Garmin client
```

Neither configuration contains Garmin credentials, tokens, MFA values, or a
repository-local token path. The untracked host configuration stores the
absolute executable path and `serve` argument; authentication keeps using the
external default token directory. All 21 tools remain discoverable so future
milestones can use the same connection, but the project policy prompts before
tools by default; only `garmin_connection_status` and `garmin_ping` have
automatic approval.

The automated Milestone 2 handshake verified stdio initialization and tool
discovery without calling Garmin data methods. The connection-only status call
succeeded with local network access. A managed shell sandbox without network
access reproduced a sanitized connection failure, so live MCP checks require a
local Codex host that can reach Garmin Connect.

During manual verification, the desktop app did not show a server configured
only in project scope even though the CLI loaded it from the repository. Adding
the same server through `codex mcp add` made it visible at host scope while the
tracked project configuration continued to supply repository-specific approval
policy. Existing tasks retain their startup tool inventory, so verification must
use a fresh task after the local client restarts.

## Authentication and token storage

1. `_client()` loads the repository-root `.env` through `python-dotenv`.
2. It reads `GARMIN_EMAIL` and `GARMIN_PASSWORD`.
3. It constructs `garminconnect.Garmin` with an MFA callback.
4. `client.login(token_directory)` reuses saved tokens or authenticates as needed.
5. The client is cached once per process with `lru_cache(maxsize=1)`.

The dedicated `garminconnect-mcp login` command supports an interactive MFA
prompt. A temporary `GARMIN_MFA_CODE` environment variable supports
non-interactive login.

Tokens default to `~/.garminconnect`, outside this repository. The location can
be changed with `GARMINCONNECT_TOKEN_DIR`. `.gitignore` excludes `.env` and the
local virtual environment, caches, build output, and package metadata. The
tracked `.env.example` contains names and empty values only.

The default secret locations are protected, but `.gitignore` does not protect an
arbitrary custom token directory placed inside the repository. Such a location
should not be used unless it is explicitly ignored.

## Dependencies

The declared runtime dependencies are:

| Dependency | Declared range | Purpose |
| --- | --- | --- |
| `garminconnect` | `>=0.3.3,<0.4` | Unofficial Garmin Connect authentication and API client |
| `mcp` | `>=1.2.0,<2` | FastMCP server and stdio transport |
| `python-dotenv` | `>=1.0.1` | Load local credentials and settings from `.env` |

The Milestone 1 environment resolved `garminconnect 0.3.11`, `mcp 1.29.1`, and
`python-dotenv 1.2.3`.

Milestone 0 found a dependency compatibility defect: a fresh install resolved
`mcp 2.1.0`, which no longer provides `mcp.server.fastmcp`. Milestone 1 fixes the
reproducibility issue with the minimal compatible upper bound, `mcp<2`. A
deliberate MCP 2.x migration remains a possible later change.

## Existing MCP tools

The server exposes 21 tools.

| Tool | Kind | Current behavior | Specification status |
| --- | --- | --- | --- |
| `garmin_connection_status` | Read, non-private | Authenticates and returns `{"ok": true}` | Meets connection-health intent; duplicate of `garmin_ping` |
| `garmin_ping` | Read, non-private | Authenticates and returns `{"ok": true}` | Meets FR-02 |
| `garmin_profile` | Read, raw/private | Returns full name and raw profile | Extra capability; intentionally private |
| `garmin_daily_stats` | Read, normalized/private | Returns compact daily measurements with explicit units and null unavailable fields | Milestone 4 complete |
| `garmin_heart_rate` | Read, normalized/private | Returns resting and daily summaries in bpm without sample arrays | Milestone 4 complete |
| `garmin_sleep` | Read, normalized/private | Returns UTC times, second-based durations, and Garmin score/status | Milestone 4 complete |
| `garmin_hrv` | Read, normalized/private | Returns one nightly summary in milliseconds | Milestone 4 complete |
| `garmin_hrv_range` | Read, normalized/private | Returns up to 14 inclusive days of HRV summaries | Milestone 4 complete |
| `garmin_body_battery` | Read, normalized/private | Returns compact Garmin-native daily summary values | Milestone 4 complete |
| `garmin_stress` | Read, normalized/private | Returns compact Garmin-native daily summary values | Milestone 4 complete |
| `garmin_recent_activities` | Read, normalized/private | Returns bounded, optionally running-only activity summaries with explicit units and null unavailable fields | Milestone 3 scope implemented and manually verified |
| `garmin_activity` | Read, normalized/private | Returns the same stable schema for one numeric activity ID | Milestone 3 scope implemented and manually verified |
| `garmin_running_activities_by_date` | Read, normalized/private | Returns running activities for an inclusive range of at most 42 days | Milestone 5 complete |
| `garmin_weekly_running_summary` | Read, aggregate/private | Returns weekly meter/second/count facts, coverage, and longest runs | Milestone 5 complete |
| `garmin_compare_running_weeks` | Read, aggregate/private | Compares adjacent Monday-Sunday weeks with absolute deltas and coverage | Milestone 5 complete |
| `garmin_compare_recent_long_runs` | Read, aggregate/private | Compares weekly greatest-distance candidates across at most five weeks | Milestone 5 complete |
| `garmin_workouts` | Read, summarized | Returns ID, name, sport, and estimated duration | Substantially covers FR-09 |
| `garmin_scheduled_workouts` | Read, summarized | Returns one calendar month's scheduled workouts | Substantially covers FR-10 |
| `garmin_schedule_workout` | Write | Schedules an existing template and summarizes the result | Partial FR-12; no local date validation or duplicate protection |
| `garmin_create_scheduled_workout` | Write | Uploads arbitrary Garmin JSON, then schedules it | Partial FR-11/FR-13; no internal schema, validation, rollback, or duplicate protection |
| `garmin_unschedule_workout` | Write/destructive | Removes a calendar assignment by scheduled-workout ID | Basic FR-14 behavior exists |

The three write tools are immediately callable MCP tools. The server does not
itself implement an approval or proposal boundary; safety therefore depends on
the MCP client and user workflow.

## Tests and checks

The default tests are offline and use synthetic data. `tests/test_server.py`
uses a fake client to cover token-path expansion, MFA behavior, dispatch helpers,
default dates, all tool wrappers, summary transforms, and CLI argument behavior.
`tests/test_private_output_scanner.py` verifies the durable-text scanner. No
default test makes a real Garmin request or write.

Milestone 0 results:

| Check | Result |
| --- | --- |
| `scripts/check-private-output.sh` | Passed |
| Fresh declared install + `python -m pytest` with MCP 2.1.0 | Failed during collection: missing `mcp.server.fastmcp` |
| `python -m pytest` with MCP 1.29.1 | Passed: 24 tests |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed: 11 files already formatted |
| `python -m compileall -q src` | Passed |

There are no opt-in integration tests, static type checker configuration, CI
workflow, or dependency lock file. The default suite is offline; the live
Milestone 3 and 4 shape probes were deliberately one-off and did not save raw
responses.

Milestone 2 adds an offline configuration test for the project-scoped Codex MCP
entry and its approval policy. Milestone 3 adds synthetic normalizer/provider
tests covering explicit units, null fields, nested summary envelopes, running
filtering, bounds, malformed responses, unknown activities, authentication,
rate limiting, and endpoint errors. Default tests never contact Garmin.

Milestone 4 adds synthetic tests for all six single-date recovery schemas, the
bounded HRV range, strict date validation, explicit units, null unavailable
fields, discarded sample arrays, malformed shapes, authentication, rate limits,
and endpoint failures. At the manual-verification stopping point, the full suite
contains 84 passing tests.

Milestone 5 adds synthetic tests for strict 42-day bounds, running-filtered date
retrieval, normalization, empty weeks, missing dates and measurements, partial
coverage, deterministic longest-run selection, adjacent-week validation,
week-over-week deltas, recent weekly longest-run comparisons, and MCP wrappers.
At the manual-verification stopping point, the suite contains 105 passing tests.

## Gap analysis against `PROJECT_SPEC.md`

| Requirement | Current state | Gap |
| --- | --- | --- |
| FR-01 Authentication | Partial | Saved-token login, MFA, and a dedicated login command exist. Live persistence and refresh behavior remain unverified. |
| FR-02 Connection verification | Implemented | Both `garmin_ping` and a duplicate status tool exist. Live behavior remains for Milestone 1/2 verification. |
| FR-03 Recent activities | Milestone 3 complete | Compact explicit-unit pagination and running filtering were manually verified; Milestone 5 adds bounded date ranges. |
| FR-04 Activity details | Milestone 3 complete | One-activity normalized lookup, unavailable fields, and safe unknown-ID handling are implemented; normalized live details were manually verified. |
| FR-05 Daily recovery | Milestone 4 complete | Compact daily statistics, heart rate, stress, and related factual summaries use explicit units and null unavailable fields. |
| FR-06 Sleep | Milestone 4 complete | Compact second-based stages, UTC times, and Garmin score/status are normalized without detailed arrays. |
| FR-07 HRV | Milestone 4 complete | Single-date and inclusive ranges up to 14 days return millisecond summaries. |
| FR-08 Body Battery | Milestone 4 complete | Compact Garmin-native charged, drained, high, low, and latest values are normalized. |
| FR-09 Existing workouts | Mostly implemented | Compact listing exists, but response-schema resilience and live behavior are unverified. |
| FR-10 Scheduled workouts | Mostly implemented | Compact monthly listing exists, but timezone/date behavior and live behavior are unverified. |
| FR-11 Create running workout | Missing as specified | Raw upload is possible only inside create-and-schedule. There is no standalone builder, internal schema, supported-step/target validation, or pre-write representation. |
| FR-12 Schedule workout | Partial | The pass-through write exists; date validation, idempotency, duplicate protection, explicit units/timezone rules, and live verification do not. |
| FR-13 Create and schedule | Partial | The two calls exist, but arbitrary Garmin JSON is accepted and partial failure can leave an uploaded template behind. |
| FR-14 Unschedule workout | Partial | The pass-through operation exists; identifier validation, error mapping, and live verification do not. |
| Training summaries | Milestone 5 complete | Bounded running retrieval, weekly aggregates with coverage, longest-run selection, and week comparisons were manually verified without coaching interpretation. |
| Weekly planner | Missing | No proposal model or deterministic planning constraints. |
| Provider boundary | Partial | Activity and recovery calls have clear provider seams; profile and workout families still directly depend on the Garmin client. |
| Normalized domain models | Partial | Activities, recovery data, and workout-list summaries are normalized; profile and later planning domains are not. |
| Error handling | Partial | Activity and recovery failures use stable secret-safe categories; other tool families still propagate third-party errors. |
| Write safety | Partial | Results are summarized and unscheduling does not delete templates, but the server has no validation, preview, idempotency, bulk guard, or approval mechanism. |
| Local-first/single-user | Implemented by design | The stdio process, local `.env`, and local token directory fit the target. |
| Offline testability | Partial | Activity and recovery normalization, validation, provider behavior, and wrappers are covered with synthetic data; future boundaries still need coverage in their milestones. |

## Recommended milestone sequence

The repository already has useful Garmin authentication and endpoint coverage, so
it should be extended rather than rewritten. The roadmap order remains suitable:

1. Authentication and token reuse were verified in Milestone 1.
2. MCP discovery and connection were verified in Milestone 2.
3. Activity normalization and its provider seam were completed and manually
   verified in Milestone 3.
4. Recovery normalization and manual Garmin comparison completed Milestone 4.
5. Milestone 5 running summaries were implemented and manually verified.
6. Stop after Milestone 5; Milestone 6 must begin only when explicitly requested.

The MCP dependency incompatibility was resolved in Milestone 1 with an upper
bound rather than a framework migration.
