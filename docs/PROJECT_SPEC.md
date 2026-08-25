# Garmin Fitness MCP — Project Specification

## 1. Objective

Build a personal MCP server that allows an MCP-capable AI client such as Codex to interact with Garmin Connect for running-training workflows.

The system should eventually support conversations such as:

```text
Analyze my training from the last four weeks.
```

```text
How was my long run compared with the previous three?
```

```text
Based on my recent training and recovery, propose my running schedule for next week.
```

```text
Create these workouts in Garmin.
```

The system should rely on an existing Garmin Connect integration where practical rather than rebuilding unofficial Garmin endpoints.

---

# 2. Product Philosophy

The MCP server is primarily a tool layer.

The language model performs high-level reasoning.

The server should provide:

* accurate data
* compact structured representations
* safe write operations
* deterministic validation

The server should not attempt to embed an entire AI coach inside the MCP implementation.

---

# 3. Primary User Flow

## Phase A — Read Garmin Data

```text
User
  ↓
Codex
  ↓
MCP tools
  ↓
Garmin Connect
```

Example:

```text
User:
Analyze my running this week.

Codex:
1. request recent activities
2. inspect relevant activities
3. optionally inspect recovery metrics
4. produce analysis
```

---

# 4. Phase B — Training Proposal

Example:

```text
User:
Plan four runs for next week.
```

Codex should retrieve relevant information and construct a proposal.

Example result:

```text
Monday
Easy run — 6 km

Wednesday
Quality session — intervals

Friday
Recovery run — 5 km

Saturday
Long run — 12 km
```

No Garmin changes occur yet.

---

# 5. Phase C — Garmin Write

After user approval:

```text
Codex
  ↓
create_running_workout
  ↓
Garmin Connect

Codex
  ↓
schedule_workout
  ↓
Garmin Calendar
  ↓
Garmin device
```

---

# 6. Functional Requirements

## FR-01 Authentication

The server must reuse authenticated Garmin sessions/tokens when possible.

The MCP process should not require interactive MFA during normal tool invocation.

Authentication refresh/setup should occur through a dedicated command or documented flow.

---

## FR-02 Connection Verification

Provide a lightweight connection-health tool.

Example:

```text
garmin_ping
```

It should verify that Garmin access is functional without exposing private health information.

---

## FR-03 Recent Activities

Provide recent Garmin activities.

Minimum normalized fields where available:

```text
activity_id
activity_type
name
start_time
distance_m
duration_s
average_hr_bpm
max_hr_bpm
average_speed
average_pace
calories
elevation_gain_m
```

---

## FR-04 Activity Details

Retrieve detailed information for an individual activity.

Running-specific useful fields may include:

```text
laps
splits
heart_rate
cadence
pace
elevation
training_effect
training_load
power
temperature
```

Only expose fields actually available from Garmin.

---

## FR-05 Daily Recovery

Provide a compact daily recovery representation containing available metrics such as:

```text
resting_hr
sleep_duration
sleep_score
hrv
body_battery
stress
training_readiness
```

Unavailable metrics must be represented clearly.

---

## FR-06 Sleep

Provide sleep information by date.

Relevant fields:

```text
sleep_start
sleep_end
duration
deep_sleep
light_sleep
rem_sleep
awake_time
sleep_score
```

---

## FR-07 HRV

Provide HRV information by date or range when available.

---

## FR-08 Body Battery

Provide Body Battery information where available.

---

## FR-09 Existing Workouts

List Garmin workouts/templates.

Return compact metadata.

---

## FR-10 Scheduled Workouts

Return workouts currently scheduled on Garmin's calendar.

---

## FR-11 Create Running Workout

Allow creation of Garmin-compatible structured running workouts.

Supported first-version step types:

```text
warmup
run
recovery
cooldown
repeat
```

Possible targets:

```text
open
time
distance
heart-rate range
pace range
```

Only implement targets confirmed to work with Garmin.

---

## FR-12 Schedule Workout

Schedule an existing Garmin workout on a specified date.

Date format:

```text
YYYY-MM-DD
```

---

## FR-13 Create and Schedule Workout

Provide a convenience operation that:

1. validates workout
2. creates workout
3. schedules workout

Failure behavior must be clear.

Avoid leaving unexpected partial state where practical.

---

## FR-14 Unschedule Workout

Support removing a workout from a date without deleting the workout template itself.

Deletion of templates is not required initially.

---

# 7. Training Summary Requirements

Provide sufficient tools so Codex can calculate:

```text
weekly distance
weekly duration
number of runs
longest run
average pace
average HR
hard-session count
easy-session count
week-over-week volume change
```

Prefer client-side reasoning from normalized activity data rather than creating one dedicated MCP tool per derived metric.

---

# 8. Weekly Training Planner

The first planner version should be proposal-only.

Inputs may include:

```text
recent 2–6 weeks of activities
current weekly volume
recent longest run
recent hard workouts
recovery information
already scheduled workouts
user constraints
```

Output should be a structured proposal.

Example internal representation:

```json
{
  "week_start": "YYYY-MM-DD",
  "sessions": [
    {
      "date": "YYYY-MM-DD",
      "type": "easy",
      "distance_km": 6,
      "notes": "Comfortable conversational effort"
    }
  ]
}
```

No Garmin writes occur as part of proposal generation.

---

# 9. Safety Requirements

## S-01

Reading health and activity information is non-destructive.

## S-02

Workout creation and scheduling are write operations.

## S-03

Destructive changes require explicit intent.

## S-04

Do not expose Garmin credentials through MCP.

## S-05

Do not persist raw health payloads unless technically necessary.

## S-06

Do not describe recovery metrics as medical diagnoses.

---

# 10. Data Model Direction

Introduce normalized domain models when extending the base repository.

Suggested models:

```text
ActivitySummary
ActivityDetail
RecoverySummary
SleepSummary
WorkoutDefinition
WorkoutStep
ScheduledWorkout
WeeklyTrainingSummary
TrainingPlan
```

Do not implement all models immediately.

Add them as required by milestones.

---

# 11. Provider Boundary

Garmin access must be replaceable.

Conceptual interface:

```text
GarminProvider
├── get_recent_activities()
├── get_activity()
├── get_daily_stats()
├── get_sleep()
├── get_hrv()
├── get_body_battery()
├── get_workouts()
├── create_workout()
├── schedule_workout()
└── unschedule_workout()
```

The MCP layer should not depend directly on undocumented HTTP endpoints.

---

# 12. Initial MCP Tool Set

Target first stable tool set:

```text
garmin_ping
garmin_recent_activities
garmin_activity
garmin_daily_stats
garmin_sleep
garmin_hrv
garmin_body_battery
garmin_workouts
garmin_scheduled_workouts
garmin_create_running_workout
garmin_schedule_workout
garmin_unschedule_workout
```

Existing upstream tool names may be preserved when appropriate.

Avoid unnecessary breaking changes.

---

# 13. Non-Functional Requirements

The project should be:

* local-first
* single-user
* easy to install
* safe with credentials
* testable without live Garmin access
* understandable by future contributors
* usable from Codex
* resilient to moderate Garmin schema changes

---

# 14. Success Criteria — MVP

MVP is complete when all of the following work:

```text
Codex:
"Show my runs from the last 7 days."
```

```text
Codex:
"Summarize my sleep, HRV, and Body Battery for the last 3 days."
```

```text
Codex:
"Compare my latest long run with my previous long run."
```

And the results match Garmin Connect closely enough for normal personal use.

The MVP is read-only.

---

# 15. Success Criteria — V1

V1 is complete when the user can say:

```text
Create a 10-minute warmup,
3 × 6-minute tempo with 3-minute recovery,
and a 10-minute cooldown for Friday.
```

Codex should:

1. convert the request into structured workout steps
2. show the intended workout
3. create the Garmin workout after approval
4. schedule it for the requested date
5. confirm the resulting Garmin workout/calendar entry

---

# 16. Success Criteria — V2

V2 is complete when the user can say:

```text
Analyze my last four weeks and propose next week's four runs.
```

After reviewing the proposal:

```text
Schedule them.
```

Codex should create and schedule the workouts through MCP.

---

# 17. Explicit Non-Goals

The project does not initially aim to:

* replace Garmin Connect
* replace a human coach
* provide medical guidance
* support arbitrary Garmin accounts
* become a hosted commercial product
* implement a mobile application
* automatically change training without the user's knowledge
