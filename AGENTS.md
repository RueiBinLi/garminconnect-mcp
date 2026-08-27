# AGENTS.md

## Project Overview

This repository implements a personal Garmin Fitness MCP Server.

The project starts from an existing open-source Garmin Connect MCP implementation rather than rebuilding Garmin authentication and API access from scratch.

The goal is to evolve the base MCP server into a reliable personal training interface that allows Codex and other MCP clients to:

1. Read Garmin activity and recovery data.
2. Normalize Garmin data into stable internal schemas.
3. Analyze recent running training.
4. Generate structured weekly training recommendations.
5. Create Garmin-compatible workouts.
6. Schedule workouts to Garmin Connect.
7. Modify future workouts safely when training conditions change.

The current priority is running training.

Strength-training app integration is explicitly out of scope for the initial versions.

---

# Runtime Usage Safety

When the user is using the Garmin MCP for normal training, activity analysis,
workout planning, or workout scheduling:

- Do not modify repository files.
- Do not edit configuration files.
- Do not install or update dependencies.
- Do not create commits or branches.
- Do not refactor code.
- Do not run destructive Git commands.
- Only invoke existing MCP tools.

Repository changes are allowed only when the user explicitly asks to develop,
fix, refactor, or extend the MCP server.

---

# Development Model

The repository is developed primarily by Codex.

The human user is responsible for:

* product decisions
* approving behavioral changes
* manually testing Garmin integration
* deciding training-policy requirements
* reviewing user-visible behavior

Codex is responsible for:

* reading the existing repository before making changes
* implementation
* refactoring
* tests
* documentation
* dependency changes
* debugging
* maintaining migration notes
* maintaining task status

Do not ask the user to manually write implementation code unless necessary.

---

# Core Principle

Do not rewrite working Garmin integration without a concrete technical reason.

Prefer:

1. understand existing implementation
2. test existing behavior
3. isolate third-party Garmin behavior
4. extend through clean abstractions
5. replace components only when necessary

The Garmin Connect interface is unofficial and may change.

All Garmin-specific behavior must therefore remain isolated behind a service/provider layer.

---

# Architecture Direction

The target architecture is:

```text
MCP Client
    |
    v
MCP Tools
    |
    v
Application Services
    |
    +----------------------+
    |                      |
    v                      v
Training Analysis      Workout Planning
    |                      |
    +----------+-----------+
               |
               v
        Garmin Provider
               |
               v
        Garmin Connect
```

Garmin API responses must not propagate directly throughout the application.

Normalize external responses before using them in higher-level training logic.

---

# Initial Scope

## Read Operations

Support reliable access to:

* recent activities
* individual activity details
* daily statistics
* heart rate
* sleep
* HRV
* Body Battery
* stress
* existing workouts
* scheduled workouts

## Write Operations

Eventually support:

* create running workout
* schedule existing workout
* create and schedule running workout
* unschedule workout

Write operations must be implemented conservatively.

---

# Out of Scope for Initial Milestones

Do not implement unless explicitly requested:

* iOS workout-log application
* Garmin Connect IQ application
* strength-training logging
* nutrition tracking
* autonomous long-term coaching
* automatic workout scheduling without user approval
* medical recommendations
* multi-user accounts
* public hosted SaaS
* database infrastructure unless it becomes necessary

---

# Safety Rules for Write Operations

Reading Garmin data may happen automatically.

Writing or deleting Garmin workouts requires explicit user intent.

Never silently:

* delete workouts
* modify existing scheduled workouts
* overwrite templates
* reschedule workouts
* create large numbers of workouts

Before destructive or bulk changes, expose exactly what will change.

Prefer idempotent operations whenever possible.

---

# Garmin Credentials and Private Data

Never commit:

* Garmin email
* Garmin password
* MFA codes
* OAuth tokens
* session cookies
* raw health exports
* private Garmin payloads

Secrets must stay outside version control.

Ensure `.gitignore` covers all local authentication files.

Do not include real personal Garmin data in:

* tests
* documentation
* GitHub issues
* examples
* fixture files

Use synthetic fixtures.

---

# Data Normalization

Do not expose unnecessarily large raw Garmin payloads to the MCP client.

Create normalized structures where useful.

Examples:

```text
ActivitySummary
ActivityDetail
DailyRecovery
SleepSummary
HRVSummary
RunningMetrics
WorkoutSummary
ScheduledWorkout
```

Preserve raw access only where debugging genuinely requires it.

Normalized representations should use explicit units.

Examples:

```text
distance_m
duration_s
pace_s_per_km
heart_rate_bpm
cadence_spm
elevation_gain_m
```

Avoid ambiguous field names.

---

# Training Analysis

Training analysis must distinguish factual measurements from interpretation.

Example:

Fact:

```text
Average heart rate: 158 bpm
Distance: 10.2 km
```

Interpretation:

```text
The session appears substantially harder than recent easy runs.
```

Do not invent missing Garmin metrics.

If a field is unavailable, represent it as unavailable rather than estimating it unless the feature explicitly requires estimation.

---

# Training Planner

Do not initially encode a complicated coaching algorithm.

Start with deterministic constraints and transparent rules.

Possible inputs include:

* recent weekly distance
* recent activity frequency
* long-run distance
* pace
* heart rate
* training load where available
* sleep
* HRV
* Body Battery
* recent hard sessions
* scheduled workouts

The planner should produce a proposal before Garmin write operations.

The user should be able to inspect the proposal first.

---

# MCP Tool Design

Prefer narrow, composable tools.

Good:

```text
garmin_recent_activities
garmin_activity
garmin_daily_recovery
garmin_workouts
garmin_scheduled_workouts
create_running_workout
schedule_workout
```

Avoid overly broad tools such as:

```text
do_everything_for_my_training
```

Tool descriptions must clearly state:

* what data is returned
* whether the operation writes data
* expected date format
* units
* important limitations

---

# Error Handling

Return useful errors for:

* authentication expiration
* Garmin endpoint failure
* malformed Garmin response
* unknown activity
* unknown workout
* invalid workout structure
* unsupported workout step
* scheduling failure
* rate limiting

Do not expose secret values inside exception messages.

---

# Testing Strategy

Tests should be layered.

## Unit Tests

Use synthetic Garmin responses for:

* parsers
* normalization
* workout serialization
* validation
* training-analysis logic

## Integration Tests

Integration tests may use the real Garmin account only when explicitly invoked.

Do not make real Garmin requests during the default test suite.

## Write Tests

Never create, modify, or delete real Garmin workouts during normal automated tests.

Real write verification must be manual or explicitly opt-in.

---

# Required Verification After Every Milestone

After each milestone:

1. run the full automated test suite
2. run lint/static checks
3. report changed files
4. report known limitations
5. provide a concise manual verification checklist
6. wait for the user's manual Garmin verification when physical-device behavior is involved

Do not proceed past an integration milestone if the preceding behavior cannot be verified.

---

# Documentation Responsibilities

Keep the following current:

* `README.md`
* `docs/ARCHITECTURE.md`
* `docs/ROADMAP.md`
* `docs/MANUAL_TESTING.md`
* tool documentation
* setup instructions

Update documentation in the same change as behavior changes.

---

# Coding Style

Follow the conventions already established by the repository unless there is a strong reason to change them.

Prefer:

* small modules
* typed interfaces
* descriptive names
* explicit units
* dependency injection around Garmin access
* pure functions for transformation and analysis
* minimal hidden global state

Avoid unnecessary abstractions before they are needed.

---

# Dependency Policy

Before adding a dependency:

1. check whether the repository already solves the requirement
2. determine whether the standard library is sufficient
3. justify the dependency
4. prefer actively maintained libraries

Do not replace major Garmin dependencies casually.

---

# Commit Scope

Keep changes focused.

Preferred progression:

```text
existing behavior verification
→ normalization
→ read tools
→ Codex MCP verification
→ workout creation
→ workout scheduling
→ training summary
→ weekly planner
```

Do not implement the entire roadmap in one change.

---

# Decision Rule

When multiple approaches are possible:

1. choose the simplest reliable approach
2. preserve compatibility with the existing Garmin provider
3. optimize for maintainability
4. document uncertainty
5. ask the user only when the decision materially changes product behavior

Codex may make ordinary engineering decisions independently.
