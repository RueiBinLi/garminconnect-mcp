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

* [ ] Determine current supported Codex MCP configuration.
* [ ] Add the Garmin server.
* [ ] Start a new Codex session.
* [ ] Verify Garmin MCP tools are discoverable.
* [ ] Run the connection tool from Codex.
* [ ] Document setup in `README.md`.

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

* [ ] Test recent activity retrieval.
* [ ] Test individual activity retrieval.
* [ ] Inspect Garmin response size.
* [ ] Introduce normalized activity structures if upstream output is too noisy.
* [ ] Preserve useful running metrics.
* [ ] Add synthetic unit-test fixtures.
* [ ] Handle missing fields gracefully.

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

---

# Milestone 4 — Recovery Data

## Goal

Allow Codex to inspect recovery-related Garmin metrics.

## Tasks

* [ ] Verify daily stats.
* [ ] Verify sleep.
* [ ] Verify HRV.
* [ ] Verify Body Battery.
* [ ] Verify heart-rate data.
* [ ] Verify stress data where available.
* [ ] Normalize high-value metrics.
* [ ] Add date validation.
* [ ] Test unavailable-data handling.

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

---

# Milestone 5 — Training Summary

## Goal

Let Codex reason effectively about several weeks of running.

## Tasks

* [ ] Ensure date-range activity retrieval is practical.
* [ ] Ensure normalized output is compact enough for multi-week queries.
* [ ] Add helper functions where repeated calculations justify them.
* [ ] Support weekly distance summaries.
* [ ] Support longest-run identification.
* [ ] Support week-over-week comparison.
* [ ] Add tests for aggregation logic.

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

---

# Milestone 6 — Workout Read Operations

## Goal

Inspect Garmin workout templates and calendar state.

## Tasks

* [ ] List workout templates.
* [ ] List scheduled workouts.
* [ ] Normalize workout metadata.
* [ ] Verify dates and timezone handling.
* [ ] Test missing/empty schedules.

## Manual Tests

Ask:

```text
What running workouts do I currently have in Garmin?
```

```text
What workouts are scheduled this week?
```

Compare with Garmin Connect.

---

# Milestone 7 — Running Workout Builder

## Goal

Create structured running workouts safely.

## Initial Supported Steps

* [ ] warmup
* [ ] run
* [ ] recovery
* [ ] cooldown
* [ ] repeat

## Initial Supported Durations

* [ ] time
* [ ] distance
* [ ] open-ended where Garmin supports it

## Initial Supported Targets

Investigate and implement only verified Garmin-compatible targets.

Potential targets:

* [ ] no target
* [ ] heart-rate range
* [ ] pace range

## Tasks

* [ ] Define internal workout schema.
* [ ] Implement validation.
* [ ] Implement Garmin serialization.
* [ ] Add synthetic serialization tests.
* [ ] Prevent malformed workout submission.
* [ ] Provide readable pre-write representation.

## Done When

A workout can be generated deterministically from an internal definition.

Do not schedule it yet.

---

# Milestone 8 — Real Workout Creation

## Goal

Create one test workout in the user's Garmin account.

## Safety Rule

Do not perform real Garmin writes without explicit user approval.

## Manual Test Workout

Use a clearly identifiable test name such as:

```text
MCP TEST - Easy Run
```

Use a harmless short workout.

## Manual Verification

* [ ] Workout appears in Garmin Connect.
* [ ] Steps match intended structure.
* [ ] Targets match.
* [ ] Units are correct.
* [ ] Workout can be opened normally.
* [ ] No duplicate unexpected workouts were created.

---

# Milestone 9 — Workout Scheduling

## Goal

Schedule an existing workout on a Garmin calendar date.

## Tasks

* [ ] Implement date validation.
* [ ] Schedule workout.
* [ ] Confirm returned Garmin state.
* [ ] Implement unscheduling.
* [ ] Add duplicate protection where possible.
* [ ] Document timezone behavior.

## Manual Verification

* [ ] Workout appears on intended Garmin Connect date.
* [ ] Workout syncs to the Garmin device.
* [ ] Workout can be opened from the watch.
* [ ] Unscheduling removes calendar assignment without deleting the template.

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

* [ ] Proposal must be visible before write when requested.
* [ ] Validation occurs before Garmin creation.
* [ ] Errors are clearly reported.
* [ ] Avoid accidental duplicate creation.

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
