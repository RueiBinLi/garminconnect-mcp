# Garmin Fitness MCP — Implementation Roadmap

## Development Strategy

Do not rebuild the entire server.

Start from the selected existing Garmin MCP repository.

Codex must first inspect and validate upstream behavior before adding new functionality.

Each milestone should be a separate, reviewable change.

---

# Milestone 0 — Upstream Audit

## Goal

Understand exactly what the existing repository already provides.

## Tasks

* [x] Read the complete README.
* [x] Read `AGENTS.md` if upstream contains one.
* [x] Inspect project structure.
* [x] Identify Garmin authentication implementation.
* [x] Identify MCP framework and transport.
* [x] List every existing MCP tool.
* [x] Identify read versus write tools.
* [x] Identify tests.
* [x] Identify Garmin library dependency.
* [x] Identify where tokens are stored.
* [x] Verify `.gitignore` protects secrets.
* [x] Run existing tests.
* [x] Run lint/static checks.
* [x] Document existing architecture in `docs/ARCHITECTURE.md`.
* [x] Document gaps between upstream capabilities and `PROJECT_SPEC.md`.

## Done When

Codex produces a concise audit report and no functionality has been rewritten unnecessarily.

---

# Milestone 1 — Local Garmin Authentication

## Goal

Establish reliable access to the user's Garmin account.

## Tasks

* [x] Set up the local environment.
* [x] Install dependencies with the MCP 1.x compatibility bound.
* [x] Perform Garmin authentication using the repository's supported flow.
* [x] Support MFA if required.
* [x] Verify the default token/session directory is outside version control.
* [x] Run connection smoke test.
* [x] Verify authentication survives MCP process restart.
* [x] Add troubleshooting notes.

Status: completed on 2026-08-26. The user confirmed live authentication, the
connection smoke test, saved-token reuse after a process restart, and secret-safe
Git state. No Garmin write operation was used.

## Manual Test

* [x] Authenticate successfully.
* [x] Restart the terminal/process.
* [x] Run connection check again.
* [x] Confirm no password or token appears in Git-tracked files.

---

# Milestone 2 — Codex MCP Connection

## Goal

Connect the local server to Codex.

## Tasks

* [x] Determine current supported Codex MCP configuration.
* [x] Add the Garmin server at Codex host scope and add a trusted-project stdio
      policy configuration.
* [x] Start a new Codex session.
* [x] Verify Garmin MCP tools are discoverable through an automated stdio
      handshake.
* [x] Run only the connection-safe status tool through the MCP connection.
* [x] Document setup in `README.md`.

Status: completed on 2026-08-26. The first desktop manual attempt exposed a
project-versus-host configuration scope mismatch, which was resolved with
host-level registration. The user then confirmed from a restarted local client
and new task that `garmin` was enabled and the connection worked. No private
Garmin fitness data or workout write operation was used.

## Manual Test

Ask Codex:

```text
Check whether my Garmin MCP connection is working.
```

Expected:

* MCP tool executes successfully.
* No private profile data is returned unless requested.

---

# Milestone 3 — Activity Data

## Goal

Provide reliable recent running data.

## Tasks

* [x] Test recent activity retrieval with a five-item, read-only structural probe.
* [x] Test one selected recent run through the individual activity endpoint.
* [x] Inspect Garmin response size without saving or displaying payload values.
* [x] Introduce compact normalized activity structures behind a provider seam.
* [x] Preserve useful running metrics with explicit units.
* [x] Add synthetic unit-test fixtures.
* [x] Handle unavailable fields, malformed responses, unknown activities,
      authentication failures, rate limits, and endpoint failures gracefully.
* [x] Add bounded offset pagination and running-only filtering.

Status: completed on 2026-08-26. The user confirmed that the latest five
normalized activities, running-only filtering, one selected run's normalized
details, and unavailable-field behavior all matched Garmin Connect. No Garmin
write operation was used. Canonical schema units remain meters and seconds;
clients may present distance in kilometers and pace as `MM:SS/km`.

## Manual Tests

Ask Codex:

```text
Show my latest five Garmin activities.
```

Then:

```text
Only show running activities.
```

Then:

```text
Give me details for my latest run.
```

Compare results with Garmin Connect.

Manual acceptance:

* [x] Latest five normalized activities match Garmin Connect.
* [x] Running-only results contain only running activities.
* [x] One selected recent run's normalized details match Garmin Connect.
* [x] Garmin fields unavailable for an activity appear as `null`.

---

# Milestone 4 — Recovery Data

## Goal

Allow Codex to inspect recovery-related Garmin metrics.

## Tasks

* [x] Inspect daily-statistics response structure with a minimal read-only probe.
* [x] Inspect sleep response structure with a minimal read-only probe.
* [x] Inspect single-date and bounded-range HRV response structures.
* [x] Inspect Body Battery response structure with a minimal read-only probe.
* [x] Inspect heart-rate response structure with a minimal read-only probe.
* [x] Inspect stress response structure with a minimal read-only probe.
* [x] Normalize high-value factual metrics with explicit units and native scales.
* [x] Add strict date and 14-day inclusive HRV-range validation.
* [x] Test unavailable and malformed-data handling with synthetic fixtures.
* [x] Complete user manual verification against Garmin Connect.

Status: completed on 2026-08-26. The user confirmed normalized sleep, the last
three available HRV summaries, today's Body Battery, heart-rate and stress for a
selected date, and unavailable-field behavior against Garmin Connect. No Garmin
write or delete operation was used.

## Manual Tests

Ask:

```text
How did I sleep last night?
```

```text
Show my HRV for the last three available days.
```

```text
What was my Body Battery today?
```

Compare against Garmin Connect.

Manual acceptance:

* [x] One recent night's normalized sleep matches Garmin Connect.
* [x] The last three available normalized HRV summaries match Garmin Connect.
* [x] Today's normalized Body Battery matches Garmin Connect.
* [x] Heart-rate and stress summaries for one selected date match Garmin Connect.
* [x] Unavailable fields are present as `null` and are not estimated.

---

# Milestone 5 — Training Summary

## Goal

Let Codex reason effectively about several weeks of running.

## Tasks

* [x] Add strict inclusive date-range retrieval with a conservative 42-day cap.
* [x] Use the existing compact canonical activity schema for multi-week queries.
* [x] Keep Garmin parsing in the provider/normalization boundary.
* [x] Add pure weekly distance, duration, count, and coverage aggregation.
* [x] Add deterministic longest-run identification from supplied distance.
* [x] Add adjacent week-over-week comparison.
* [x] Add bounded recent weekly longest-run comparison.
* [x] Add synthetic tests for aggregation, missing data, validation, and errors.
* [x] Complete user manual verification against Garmin Connect.

Status: completed on 2026-08-26. The user confirmed all observable live cases:
bounded running retrieval, weekly facts, adjacent-week comparison, longest-run
identification, recent weekly longest-run comparison, empty ranges, and
unavailable fields. No Garmin write or delete operation was used.

## Manual Tests

Ask:

```text
Summarize my running during the last four weeks.
```

```text
Compare this week's running volume with last week's.
```

```text
Compare my latest long run with my previous three long runs.
```

Manual acceptance:

* [x] One recent bounded running range matches Garmin Connect.
* [x] One weekly distance, duration, and count summary matches.
* [x] One adjacent week-over-week comparison matches.
* [x] The bounded range's longest run is identified correctly.
* [x] The latest weekly longest-run comparison follows the documented rule.
* [x] Empty ranges and unavailable measurements retain explicit coverage.

---

# Milestone 6 — Workout Read Operations

## Goal

Inspect Garmin workout templates and calendar state.

## Tasks

* [x] Implement bounded saved-workout template pages.
* [x] Implement inclusive scheduled-workout ranges up to 31 days over Garmin's
      month endpoint.
* [x] Normalize compact workout metadata with explicit units and nulls.
* [x] Add Garmin endpoint running-only filtering with a defensive normalized
      check and explicit source/result counts.
* [x] Add strict validation, deterministic ordering, known-envelope parsing,
      empty results, and secret-safe failure mapping.
* [x] Add synthetic normalizer, provider, and MCP wrapper tests.
* [x] Update README, architecture, manual testing, and roadmap documentation.
* [x] Verify dates and timezone handling.
* [x] Manually verify missing/empty saved pages and schedules where observable.

Status: complete and manually verified on 2026-08-27. Bounded saved pages,
running-only filtering, scheduled ranges, compact/null fields, empty results,
strict MCP validation, date-only calendar semantics, and current Garmin “My
Workouts” pagination and ordering all passed private comparison. No Garmin
write or delete operation was used, and no private values were recorded.

## Manual Tests

Ask:

```text
What running workouts do I currently have in Garmin?
```

```text
What workouts are scheduled this week?
```

Compare with Garmin Connect.

Also verify one bounded saved page, endpoint running filtering, one bounded
calendar range, normalized fields and explicit nulls, observable empty results,
and rejection of invalid pagination and ranges. Keep all returned private values
out of durable output.

---

# Milestone 7 — Running Workout Builder

## Goal

Create structured running workouts safely.

## Initial Supported Steps

* [x] warmup
* [x] run
* [x] recovery
* [x] cooldown
* [x] repeat

## Initial Supported Durations

* [x] time using `duration_s`
* [x] distance using `distance_m`
* [x] open-ended using the verified lap-button condition

## Initial Supported Targets

Investigate and implement only verified Garmin-compatible targets.

Potential targets:

* [x] no target
* [x] heart-rate range using integer bpm bounds
* [x] pace range using seconds-per-kilometer bounds

## Tasks

* [x] Define a strict internal running-workout schema with explicit units.
* [x] Implement deterministic validation, expansion, and aggregation.
* [x] Implement an internal Garmin serializer behind a dedicated boundary.
* [x] Add synthetic serialization, invalid-input, and boundary tests.
* [x] Reject malformed and unsupported definitions before any client call.
* [x] Provide `garmin_preview_running_workout` without Garmin JSON or network access.
* [x] Complete the manual offline preview checklist.

## Done When

A workout can be generated deterministically from an internal definition. The
implementation, offline automated checks, and manual preview checklist are
complete.

Do not schedule it yet.

---

# Milestone 8 — Real Workout Creation

## Goal

Create one test workout in the user's Garmin account.

## Safety Rule

Do not perform real Garmin writes without explicit user approval.

## Tasks

* [x] Add `garmin_create_running_workout(definition, confirmed=false)` using the
      exact Milestone 7 strict model and serializer.
* [x] Validate the whole definition before client construction.
* [x] Require a strict explicit Boolean before one real upload.
* [x] Keep upload and secret-safe error mapping behind the workout provider.
* [x] Return only compact normalized facts with `scheduled=false`.
* [x] Add offline synthetic tests for no-write defaults, validation, exact
      serializer input, one-call/no-retry behavior, malformed responses,
      privacy filtering, safe errors, and unreachable calendar/device writes.
* [x] Update Milestone 8 documentation and offline verification instructions.
* [x] Receive explicit approval for the exact synthetic proposal.
* [x] Invoke the validated creation tool exactly once without automatic retry.
* [x] Complete manual Garmin Connect verification.
* [x] Rerun all required checks, commit the focused change, and push to
      `origin/main` only after manual verification passes.

Status: completed and manually verified on 2026-08-27. Exactly one explicitly
approved synthetic running workout was created successfully and remained
unscheduled. No retry, duplicate, calendar change, device push, modification,
unscheduling, or deletion occurred. Milestone 9 has not started.

## Manual Test Workout

Use a clearly identifiable test name such as:

```text
MCP TEST - Easy Run
```

Use a harmless short workout.

## Manual Verification

* [x] Workout appears in Garmin Connect.
* [x] Steps match intended structure.
* [x] Targets match.
* [x] Units are correct.
* [x] Workout can be opened normally.
* [x] No duplicate unexpected workouts were created.
* [x] Workout is not scheduled and no calendar or device state changed.

---

# Milestone 9 — Workout Scheduling

## Goal

Schedule an existing workout on a Garmin calendar date.

## Tasks

* [x] Implement strict single-ID and Garmin calendar-date validation.
* [x] Add an offline schedule preview and strict confirmation boundary.
* [x] Implement exactly-one scheduling behind the workout provider.
* [x] Normalize and validate the returned Garmin assignment state.
* [x] Implement separately confirmed, assignment-only unscheduling.
* [x] Add exact workout/date duplicate protection.
* [x] Block the installed dependency's HTTP-401 write replay path.
* [x] Add offline synthetic MCP/provider safety tests.
* [x] Document date-only/timezone and device-synchronization behavior.
* [x] Receive explicit approval and invoke one exact live schedule operation.
* [x] Complete manual scheduling verification.
* [x] Receive separate approval and invoke one exact live unschedule operation.
* [x] Complete manual unscheduling verification.
* [x] Rerun checks, mark complete, and commit the focused change.
* [ ] Push to `origin/main` only after explicit authorization.

Status: completed and manually verified on 2026-08-27. Exactly one existing test
workout was scheduled after exact approval and removed after a second approval.
The template remained intact, no duplicate or unrelated calendar change was
observed, and no explicit device-push call occurred. Private assignment values
are intentionally omitted. At that completion checkpoint, Milestone 10 had not
started.

## Manual Verification

* [x] Workout appears on intended Garmin Connect date.
* [x] Garmin's normal synchronization behavior is unchanged; no server push.
* [x] Underlying workout remains available and opens normally.
* [x] Unscheduling removes calendar assignment without deleting the template.

---

# Milestone 10 — Create and Schedule Workflow

## Goal

Support:

```text
Create this workout and put it on Friday.
```

## Flow

```text
User request
→ Codex creates proposed structured workout
→ user reviews
→ create workout
→ schedule workout
→ verify result
```

## Requirements

* [x] Add a fully offline exact proposal for one strict `WorkoutDefinition` and
      one strict Garmin calendar date.
* [x] Require strict explicit confirmation before constructing a client or
      making any network request.
* [x] Validate the complete definition, expanded limits, aggregates, date,
      confirmation, and unknown fields before writing.
* [x] Upload exactly one serializer-produced workout and schedule only its
      returned validated ID at most once.
* [x] Reuse normalized exact-duplicate schedule detection.
* [x] Guard both upload and scheduling against dependency HTTP-401 replay.
* [x] Preserve a newly created unscheduled workout after scheduling failure or
      uncertainty; never retry, roll back, delete, or clean up automatically.
* [x] Return compact normalized success or partial-failure state only.
* [x] Add offline synthetic MCP/provider coverage and update documentation.
* [x] Receive explicit approval for one exact synthetic proposal and invoke the
      combined tool once.
* [x] Complete manual Garmin Connect verification.
* [x] Rerun checks, mark complete, and commit the focused change.
* [ ] Push to `origin/main` only after explicit authorization.

Status: completed and manually verified on 2026-08-27. The first approved call
stopped on expired authentication; manual inspection confirmed that no test
workout existed. After saved-login refresh and a new exact approval, exactly one
synthetic running workout was created and scheduled on the approved date. Manual
verification confirmed the template, ordered steps, calendar assignment, lack
of duplicates or unrelated changes, and normal Garmin device synchronization.
No automatic retry, rollback, cleanup, unscheduling, deletion, modification, or
device push occurred. Private identifiers are intentionally omitted. Reliable
creation deduplication remains unavailable without a stable Garmin idempotency
key or local database. Milestone 11 has not started.

---

# Milestone 11 — Weekly Training Proposal

## Goal

Generate a proposed next week based on recent Garmin data.

## Inputs

Use available information such as:

* [ ] recent run frequency
* [ ] recent weekly distance
* [ ] recent longest run
* [ ] hard sessions
* [ ] recovery metrics
* [ ] already scheduled workouts
* [ ] explicit user constraints

## Output

Produce a structured weekly proposal.

No automatic Garmin writes.

---

# Milestone 12 — Weekly Plan Scheduling

## Goal

Allow the user to approve an entire proposed week.

Example:

```text
Schedule that plan.
```

## Requirements

* [ ] Show the final session list.
* [ ] Validate all sessions before writing.
* [ ] Create sessions individually.
* [ ] Schedule each session.
* [ ] Report successes and failures separately.
* [ ] Avoid silently retrying destructive operations.

---

# Future Milestones

Possible later work:

* training-plan adjustment after missed runs
* recovery-aware rescheduling
* richer pace-zone support
* heart-rate zone support
* race-goal-aware planning
* workout-history comparisons
* workout deduplication
* caching
* remote deployment
* iPhone workout-log integration

These are not current priorities.
