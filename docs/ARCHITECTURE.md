# Garmin Connect MCP — Architecture and Upstream Audit

## Milestone 0 scope

This document records the repository as audited on 2026-08-25. Milestone 0
changes documentation only; it does not add or change MCP behavior.

## Repository structure

```text
garminconnect-mcp/
├── src/garminconnect_mcp/server.py  # Authentication, Garmin calls, MCP tools, CLI
├── tests/test_server.py             # Synthetic unit tests with a fake Garmin client
├── tests/test_private_output_scanner.py
├── scripts/check-private-output.sh  # Durable-text privacy scanner
├── docs/                            # Client setup, specification, and roadmap
├── pyproject.toml                   # Package metadata and dependencies
├── .env.example                     # Local credential configuration template
└── .gitignore                       # Local secret/build/cache exclusions
```

The implementation is intentionally small. All runtime behavior currently lives
in `server.py`; there are no separate provider, application-service, domain-model,
analysis, or planning modules.

## Current runtime architecture

```text
MCP client
    │ stdio
    ▼
FastMCP tool functions (`server.py`)
    │ direct method dispatch through `_call` / `_call_first`
    ▼
Cached `garminconnect.Garmin` client
    │ unofficial Garmin Connect behavior
    ▼
Garmin Connect
```

`FastMCP("Garmin Connect")` supplies the MCP framework. The console entry point
is `garminconnect-mcp = garminconnect_mcp.server:main`. With no command, or with
`serve`, `main()` calls `mcp.run()`. The project documentation and bundled client
configurations use the default stdio transport.

This differs from the target architecture in `AGENTS.md`: MCP tools call the
third-party client directly, so there is not yet a replaceable Garmin provider
boundary or an application-service layer. Most read responses also pass raw
Garmin dictionaries directly to the MCP client.

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
| `mcp` | `>=1.2.0` | FastMCP server and stdio transport |
| `python-dotenv` | `>=1.0.1` | Load local credentials and settings from `.env` |

The audit environment resolved `garminconnect 0.3.11` and
`python-dotenv 1.2.3`.

There is a dependency compatibility defect: a fresh install resolved `mcp 2.1.0`,
which no longer provides `mcp.server.fastmcp`. Test collection then failed with
`ModuleNotFoundError`. Installing the latest 1.x release (`mcp 1.29.1`) made the
entire existing suite pass. The project needs either an upper bound on MCP or a
deliberate migration to MCP 2.x in a later change.

## Existing MCP tools

The server exposes 16 tools.

| Tool | Kind | Current behavior | Specification status |
| --- | --- | --- | --- |
| `garmin_connection_status` | Read, non-private | Authenticates and returns `{"ok": true}` | Meets connection-health intent; duplicate of `garmin_ping` |
| `garmin_ping` | Read, non-private | Authenticates and returns `{"ok": true}` | Meets FR-02 |
| `garmin_profile` | Read, raw/private | Returns full name and raw profile | Extra capability; intentionally private |
| `garmin_daily_stats` | Read, raw/private | Returns raw daily statistics for a date | Partial FR-05; not normalized recovery data |
| `garmin_heart_rate` | Read, raw/private | Returns raw heart-rate data for a date | Required read exists, but is not normalized |
| `garmin_sleep` | Read, raw/private | Returns raw sleep data for a date | Partial FR-06 |
| `garmin_hrv` | Read, raw/private | Returns raw HRV data for a date | Partial FR-07; no range interface |
| `garmin_body_battery` | Read, raw/private | Returns raw Body Battery data for a date | Partial FR-08 |
| `garmin_stress` | Read, raw/private | Returns raw stress data for a date | Required read exists, but is not normalized |
| `garmin_recent_activities` | Read, raw/private | Returns paginated raw activities | Partial FR-03 |
| `garmin_activity` | Read, raw/private | Returns raw details by activity ID | Partial FR-04 |
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

There are no opt-in integration tests, live Garmin smoke tests, static type
checker configuration, CI workflow, dependency lock file, date-validation tests,
error-mapping tests, or normalized-schema tests.

## Gap analysis against `PROJECT_SPEC.md`

| Requirement | Current state | Gap |
| --- | --- | --- |
| FR-01 Authentication | Partial | Saved-token login, MFA, and a dedicated login command exist. Live persistence and refresh behavior remain unverified. |
| FR-02 Connection verification | Implemented | Both `garmin_ping` and a duplicate status tool exist. Live behavior remains for Milestone 1/2 verification. |
| FR-03 Recent activities | Partial | Raw pagination exists; required normalized fields, explicit units, compact output, date-range support, and graceful missing-field handling do not. |
| FR-04 Activity details | Partial | Raw detail retrieval exists; no stable activity-detail model or selected running metrics. |
| FR-05 Daily recovery | Partial | Raw daily stats and separate recovery endpoints exist; no compact combined recovery representation. |
| FR-06 Sleep | Partial | Raw date lookup exists; no normalized sleep schema or explicit unavailable values. |
| FR-07 HRV | Partial | Raw single-date lookup exists; no normalized date-range result. |
| FR-08 Body Battery | Partial | Raw single-date lookup exists; no normalized representation. |
| FR-09 Existing workouts | Mostly implemented | Compact listing exists, but response-schema resilience and live behavior are unverified. |
| FR-10 Scheduled workouts | Mostly implemented | Compact monthly listing exists, but timezone/date behavior and live behavior are unverified. |
| FR-11 Create running workout | Missing as specified | Raw upload is possible only inside create-and-schedule. There is no standalone builder, internal schema, supported-step/target validation, or pre-write representation. |
| FR-12 Schedule workout | Partial | The pass-through write exists; date validation, idempotency, duplicate protection, explicit units/timezone rules, and live verification do not. |
| FR-13 Create and schedule | Partial | The two calls exist, but arbitrary Garmin JSON is accepted and partial failure can leave an uploaded template behind. |
| FR-14 Unschedule workout | Partial | The pass-through operation exists; identifier validation, error mapping, and live verification do not. |
| Training summaries | Missing | No weekly aggregation, longest-run comparison, session classification, or week-over-week calculations. |
| Weekly planner | Missing | No proposal model or deterministic planning constraints. |
| Provider boundary | Missing | Tool functions depend directly on `garminconnect.Garmin` and its method names. |
| Normalized domain models | Mostly missing | Only workout-list summaries are normalized; health and activity payloads remain raw. |
| Error handling | Missing as a layer | Third-party exceptions generally propagate without stable categories or secret-aware translation. |
| Write safety | Partial | Results are summarized and unscheduling does not delete templates, but the server has no validation, preview, idempotency, bulk guard, or approval mechanism. |
| Local-first/single-user | Implemented by design | The stdio process, local `.env`, and local token directory fit the target. |
| Offline testability | Partial | Existing wrappers are well covered with fakes, but future normalizers, validation, provider behavior, and integration boundaries have no coverage yet. |

## Recommended milestone sequence

The repository already has useful Garmin authentication and endpoint coverage, so
it should be extended rather than rewritten. The roadmap order remains suitable:

1. Verify authentication and token reuse manually without changing the provider.
2. Verify MCP discovery and connection from Codex.
3. Introduce focused normalization at the activity and recovery boundaries.
4. Extract a provider seam when higher-level logic requires it.
5. Add validated workout models before relying on existing write pass-throughs.

The MCP dependency incompatibility should be resolved before treating a fresh
installation as reproducible, but that fix is intentionally outside Milestone 0.
