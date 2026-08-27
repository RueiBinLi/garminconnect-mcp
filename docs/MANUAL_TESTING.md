# Activity Temperature and Weather Observation (Pending Verification)

Use one completed activity with Garmin Connect temperature data and one with a
weather-station observation. Invoke only the two read-only tools below. Do not
save exact values, identifiers, coordinates, station names, or raw payloads.

For `garmin_activity_temperature(activity_id)`, verify:

- arithmetic average, minimum, and maximum match Garmin Connect after display
  rounding;
- sample count is plausible and no time-series array is returned;
- source is `garmin_activity_detail_directAirTemperature`;
- unavailable samples remain excluded and warnings stay factual;
- device placement, body heat, sunlight, and exposure limitations are clear.

For `garmin_activity_weather(activity_id)`, verify:

- the offset-bearing observation timestamp is preserved;
- condition and humidity match when Garmin supplies them;
- wind and temperature values are preserved without unsupported unit labels;
- `units_verified=false`;
- coordinates, station name, and raw Garmin objects are absent;
- source is `garmin_activity_weather_station`.

Confirm neither tool changes Garmin state, no private live values enter tests or
documentation, and existing aerobic-drift output remains unchanged.

---

# Recorded Laps and Aerobic Drift (Completed)

Manual verification completed on 2026-08-27 using one real running activity.
Recorded lap distances, pace, heart rate, cadence, half metrics, drift output,
and warnings behaved as expected. The activity was not steady enough for a
reliable steady-state assessment, and the tool correctly returned
`usable_for_drift_analysis=false` with a half-pace warning while preserving the
compact factual calculation. Only read-only activity lookup, split, and drift
operations were used; no Garmin or repository state changed. No private
activity identifier, date, measurement, or raw response is retained here.

Use one real steady/easy running activity. Invoke only
`garmin_activity_splits(activity_id, mode="laps")` and
`garmin_activity_aerobic_drift(activity_id)`; both are read-only.

Compare with Garmin Connect:

- recorded lap count and actual distances, including any partial final lap;
- lap moving pace, average HR, cadence, and elevation when available;
- first- and second-half distance, moving duration, pace, and time-weighted HR;
- aerobic decoupling percentage and sign;
- warnings and `usable_for_drift_analysis`;
- no workout, calendar, authentication, token, or other Garmin state changed.

Do not save or paste raw lap or time-series payloads into the repository.

---

# Milestone 12 Weekly Plan Scheduling Verification (Completed)

Milestone 12 completed manual verification on 2026-08-27 after the full offline
gate passed. One fresh read-only proposal received explicit approval of its
exact fingerprint and the confirmed operation was invoked once. The compact
result reported every requested session complete, with no partial failure,
uncertainty, or remaining session. The user inspected Garmin Connect and
confirmed that every expected workout and assignment matched, no duplicate
existed, all existing items were preserved, and no unrelated change occurred.
No cleanup was performed. No private date, bpm value, proposal value,
fingerprint, token, workout ID, schedule ID, calendar content, health fact,
account value, device value, or raw response is retained in this record.

## Required offline gate

Run all of the following before even generating a live preview:

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q src
```

Also initialize the MCP server over stdio and verify all 36 tools are
discoverable without constructing a Garmin client. With synthetic clients only,
exercise preview, `confirmed=false`, complete success, first failure, later
failure, created-but-unscheduled, and uncertain creation/scheduling. Audit the
complete call trace: one proposal-week stale-state read, followed for each
successful session by one upload, one exact duplicate read, and at most one
schedule using only the newly returned workout ID. Confirm no legacy write,
retry, rollback, cleanup, delete, modify, unschedule, clone, or device-push method
is reachable.

## Stage 1 — one fresh read-only preview

Obtain a future Monday and the complete Milestone 11 constraints from the user.
Call `garmin_preview_weekly_running_plan` once. This authorizes normalized reads
only. Show the complete compact private preview in the active conversation:

- factual training/recovery inputs and coverage;
- configured running Zone 2 bpm bounds and source;
- every user constraint and existing scheduled commitment;
- deterministic rules, calculations, warnings, and unavailable inputs;
- every proposed date, purpose, WorkoutDefinition, ordered step, target, unit,
  and aggregate;
- exact execution order and creation/schedule count;
- the `sha256:` proposal fingerprint, opaque approval token, and expiry;
- `preview_only=true`, `created=false`, and `scheduled=false`;
- the statement that no Garmin change occurred.

Do not copy any exact live value into this file, Git, logs, fixtures, summaries,
commit messages, or the eventual verification record.

## Stage 2 — exact approval and one invocation

Ask the user to explicitly approve the exact displayed fingerprint and proposal.
Approval applies to one invocation only. Without that approval, stop. After it,
call only:

```text
garmin_schedule_weekly_running_plan(
  approval_token=<opaque token from that preview>,
  proposal_fingerprint=<exact approved fingerprint>,
  confirmed=true
)
```

Invoke it once. Never retry. The tool must consume the approval, revalidate all
definitions and aggregates, reread only the normalized Monday-Sunday calendar,
and stop before writes if any commitment changed. A newly occupied proposed date
is a conflict. Never choose another date. An expired, used, mismatched, stale, or
conflicting approval requires a new preview and new explicit approval.

If execution starts, sessions must run in ascending approved date and execution
order. Stop after the first failure or uncertain result. Preserve all earlier
successes and any newly created unscheduled workout. Mark later sessions not
attempted. Do not retry, roll back, clean up, delete, move, modify, unschedule,
clone, or push anything to a device.

## Stage 3 — manual Garmin inspection

Report only the compact normalized outcome. Do not expose workout IDs or
scheduled-workout IDs unless immediate manual recovery strictly requires one.
For any uncertain result, instruct the user to inspect Garmin Connect before any
further action and never replay the approval.

Ask the user to verify in Garmin Connect:

- every expected new workout exists exactly once with the reviewed name, steps,
  targets, units, and aggregates;
- each is assigned exactly once on its approved date;
- no duplicate workout or calendar assignment exists;
- all pre-existing templates and calendar commitments remain unchanged;
- no unrelated workout, calendar, or device state changed.

Do not automatically clean up the verification workouts. Garmin creation has no
stable idempotency key; weekly execution is not transactionally atomic and an
uncertain creation cannot be safely deduplicated.

## After the user confirms success

After confirmation, mark Milestone 12 complete. Rerun every offline check, record only a
non-private pass/fail summary, report changed files and known limitations, and
commit the focused changes. Wait for separate explicit authorization before
pushing to `origin/main`. Do not begin a later milestone.

---

# Milestone 11 Weekly Proposal Verification (Read-only)

Milestone 11 was completed and manually verified on 2026-08-27. No write tool
was used during verification.

## Required offline verification before a live read

Run:

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q src
```

Also initialize the MCP server over stdio, list tools, make synthetic proposal
calls with fake clients, and audit that the proposal service exposes only the
normalized activity, HRV, scheduled-workout, and configured heart-rate-zone
reads. Do not perform a live read until every offline check passes.

## One live read-only proposal

Obtain one exact future Monday in `YYYY-MM-DD` and one constraints object from
the user. Those values authorize only the four normalized reads and proposal
generation. Call only `garmin_weekly_running_proposal`. Never call a
create, preview-create, schedule, unschedule, legacy write, upload, delete,
modify, clone, cleanup, rollback, retry, or device-push operation.

Report only the compact normalized response. Ask the user to verify the factual
training, recovery, and configured Zone 2 inputs; coverage; constraints;
preserved scheduled commitments; rules/calculations; warnings; proposed dates,
purposes, WorkoutDefinitions, ordered steps, Zone 2 targets, explicit units,
aggregates, completeness; and the statement that no Garmin workout or calendar
change occurred.

The user confirmed the compact factual inputs, coverage, constraints, absence
of scheduled commitments, deterministic calculations, four proposed sessions,
ordered distance steps, configured running Zone 2 targets, aggregates,
unavailable inputs, and absence of Garmin changes. The first live proposal was
rejected because its two-session distance split made the labelled long run
shorter than the easy run; the deterministic split was corrected and fully
retested before a new explicitly authorized read. A later extension added
strict desired-session semantics and normalized configured-zone reads, and its
four-session proposal passed manual verification. No private date, bpm value,
health measurement, identifier, calendar content, account value, device value,
or raw response is retained in this record.

All required checks were rerun after acceptance. At the time of this historical
Milestone 11 record, Milestone 12 had not started, and pushing remained subject
to separate explicit authorization.

The later naming extension was verified offline: `half_marathon` maps only to
`HM`, the strict Monday anchor is `W01`, later week numbers are deterministic,
pre-anchor proposals fail before client construction, and names contain the
two-digit week, purpose, and complete workout distance. No additional Garmin
read or write was needed.

---

# Completed Milestone 10 Safe Create-and-Schedule Verification

Milestone 10 was completed and manually verified on 2026-08-27. The default
suite remained offline and the legacy combined write tool was not used.

## Required offline verification before the one write

Run:

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q src
```

Also run the offline stdio initialization/tool-discovery check, both combined
preview/default-confirmation paths with forbidden client construction, and the
confirmed path with synthetic fake clients only. Audit pinned `garminconnect
0.3.11` source and verify one low-level POST in each upload and schedule wrapper,
no transient wrapper retry, and a fail-closed HTTP-401 replay guard for both
writes.

Offline acceptance:

- [x] Complete strict validation occurs before client construction.
- [x] Preview and false/omitted confirmation make no client, network, or write
      call.
- [x] Exactly one upload occurs and scheduling receives only its returned ID.
- [x] The duplicate read prevents another schedule call for an exact assignment.
- [x] Uncertain or malformed upload stops before scheduling and is never retried.
- [x] Schedule failure/uncertainty preserves compact partial state and never
      triggers retry, verification write, rollback, deletion, or cleanup.
- [x] Authentication, rate-limit, endpoint, unsupported-client, malformed, and
      uncertain outcomes are secret-safe.
- [x] Raw Garmin JSON, response data, owner/account metadata, URLs, tokens,
      device identifiers, unrelated IDs, and calendar payloads are absent.
- [x] Existing tools, schemas, legacy behavior, and offline tests remain intact.

## Exact proposal and approval boundary

Use a harmless unique name and short time-ended workout. Show the exact
normalized definition, ordered steps and targets, aggregates and completeness,
and one future strict `YYYY-MM-DD` date. State that exactly one new workout will
be created and only that returned workout ID will be scheduled. State that no
existing workout will be modified or deleted and no automatic retry, rollback,
cleanup, unscheduling, or device push will occur.

Warn that creation may succeed while scheduling fails, leaving one new
unscheduled workout. Garmin may later synchronize calendar state to connected
devices normally. The milestone-start prompt and provision of a date are not
approval. Wait for explicit approval of the complete dated proposal.

After approval, call only
`garmin_create_and_schedule_running_workout(..., confirmed=true)` once. Never
retry an uncertain result. If creation or scheduling is uncertain, stop and
report only known compact normalized facts; do not repair or clean up.

Manual acceptance:

- [x] Exactly one new workout template exists.
- [x] Its name, running sport, description, steps, targets, durations, and units
      match the proposal.
- [x] Exactly one calendar assignment exists on the approved date.
- [x] The assignment references the newly created workout.
- [x] No duplicate workout or assignment exists.
- [x] No existing workout was modified or deleted.
- [x] No unrelated calendar item changed.
- [x] Any device synchronization matches Garmin's normal behavior; the server
      made no explicit device-push call.

The first explicitly approved invocation stopped on expired authentication. It
was not retried, and manual inspection confirmed no matching workout existed.
After the saved login was refreshed, the complete unchanged proposal received a
new explicit approval. The combined tool was invoked once and returned compact
success state for one creation and one assignment. The user confirmed every
manual acceptance item above. No private identifier, raw response, account data,
or device value is retained in this record.

The test workout was not automatically unscheduled or deleted. All required
checks were rerun, only non-private acceptance facts were recorded, and the
focused Milestone 10 change was committed. Pushing still requires explicit
authorization. Milestone 11 has not started.

---

# Completed Milestone 9 Safe Scheduling and Unscheduling Verification

Milestone 9 was completed and manually verified on 2026-08-27. After all offline
checks passed, exactly one existing test workout was scheduled following exact
approval. The user verified the assignment, then separately approved removal of
only that assignment and verified that the underlying template remained intact.
No private identifier or calendar value is retained in this record. At that
checkpoint, Milestone 10 had not started.

## Safety boundary

Use only these Milestone 9 tools:

- `garmin_preview_workout_schedule`
- `garmin_schedule_existing_workout`
- `garmin_unschedule_existing_workout`

Do not use the legacy scheduling, combined upload-and-schedule, or unscheduling
tools. Do not create another workout, modify or delete a template, submit Garmin
JSON, call a device-push method, retry an uncertain result, or automatically
clean up the test assignment.

All IDs are private runtime inputs. Never save or repeat their values in Git,
documentation, tests, fixtures, logs, commits, summaries, or final reports.
Dates are strict Garmin calendar labels in `YYYY-MM-DD`; they are not timestamps
and carry no timezone or offset.

## Required offline verification before either write

Run:

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q src
```

Also run an offline stdio initialization and tool-discovery check, offline MCP
preview and omitted/false-confirmation calls with a forbidden client factory,
and confirmed scheduling/unscheduling calls with synthetic fake clients only.
The source audit must confirm that the installed scheduling wrappers have no
transient retry decorator. The provider's single-attempt guard must prove that
the low-level HTTP-401 refresh path stops before a second write request.

Offline acceptance:

- [x] Strict single IDs, strict dates, strict Booleans, and unknown-field
      rejection occur before client construction.
- [x] Schedule preview and false/omitted schedule confirmation construct no
      client and make no network or write call.
- [x] Confirmed synthetic scheduling performs one duplicate read and at most one
      scheduling call.
- [x] An exact workout/date duplicate is idempotent and makes no schedule call.
- [x] Malformed, missing-ID, mismatched, authentication, rate-limit, endpoint,
      unsupported-client, and uncertain synthetic outcomes are secret-safe and
      never retried.
- [x] Compact results discard Garmin payloads, account metadata, URLs, device
      identifiers, and unrelated IDs.
- [x] Unscheduling preview reads exactly one normalized assignment and performs
      no write.
- [x] Confirmed synthetic unscheduling re-reads that assignment and invokes
      unscheduling once without deleting its template.
- [x] No upload, create, clone, modify, template-delete, device-push, retry,
      rollback, or automatic cleanup path is invoked.
- [x] Existing schemas, legacy tools, and tests retain their behavior.

## Stage 1 — exact scheduling proposal and approval

Use the existing Milestone 8 test workout. Obtain privately at runtime:

- its exact workout ID;
- one exact future `YYYY-MM-DD` Garmin calendar date.

Show the user only the exact private proposal in the active conversation:

- `workout_id`;
- `scheduled_date`;
- exactly one existing workout will be scheduled;
- an exact same-workout/same-date duplicate will cause no write;
- no workout will be created, uploaded, cloned, modified, deleted, or directly
  pushed to a device;
- Garmin itself may synchronize the calendar assignment to connected devices.

Wait for explicit approval of those exact values. The milestone-start request
is not approval. After approval, invoke only
`garmin_schedule_existing_workout(..., confirmed=true)` once. Do not retry an
uncertain result. Report only its compact normalized result.

Manual scheduling acceptance:

- [x] Exactly one assignment appeared on the intended Garmin calendar date.
- [x] It referenced the correct existing test workout.
- [x] No duplicate assignment existed.
- [x] The underlying workout was not modified.
- [x] No unrelated calendar item changed.
- [x] Any device synchronization matched Garmin's normal behavior; this server
      made no explicit device-push call.

Do not automatically unschedule. Wait for the user's explicit confirmation that
all scheduling checks passed.

## Stage 2 — exact unscheduling proposal and approval

After scheduling verification passes, call
`garmin_unschedule_existing_workout` with confirmation omitted/false to show the
exact normalized assignment. Wait for a second explicit approval of that
scheduled-workout ID. Then call the same tool once with `confirmed=true`. Do not
retry an uncertain result.

Manual unscheduling acceptance:

- [x] The calendar assignment was removed.
- [x] The underlying workout template still exists and opens normally.
- [x] No unrelated calendar item changed.
- [x] No duplicate or unexpected state remains.

Both checklists passed. All required checks were rerun, only non-private
acceptance facts were recorded, and the focused Milestone 9 change was committed.
Pushing to `origin/main` still requires explicit authorization. At that
checkpoint, Milestone 10 had not started.

---

# Completed Milestone 8 Validated Workout-Creation Verification

Milestone 8 was completed and manually verified on 2026-08-27. All required
offline checks passed, followed by exactly one explicitly approved call to
`garmin_create_running_workout` with the exact synthetic definition below and
`confirmed=true`. The creation succeeded without a retry.

## Offline safety boundary

Before approval, use `garmin_preview_running_workout` or call
`garmin_create_running_workout` only with `confirmed` omitted/false. Both paths
must construct no Garmin client for creation and make no network or write call.
The default creation response must say `created=false` and `scheduled=false`.

Offline verification uses only synthetic fake clients. It proves that a
confirmed call uploads the exact deterministic Milestone 7 serializer output
once, filters the response, maps safe failures, performs no retry or rollback,
and cannot reach scheduling, modification, unscheduling, deletion, calendar,
or device-push methods.

Run:

```bash
scripts/check-private-output.sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q src
```

Also complete the offline stdio initialization/tool-discovery check and offline
MCP calls for omitted/false confirmation and a confirmed fake-client upload.
Never use a real account for automated tests.

## Exact synthetic proposal that was approved

Name: `MCP TEST - Easy Run`

Sport: `running`

Description: omitted

Normalized ordered steps:

1. `warmup`: time, `duration_s=300`, no target
2. `run`: time, `duration_s=600`, no target
3. `cooldown`: time, `duration_s=300`, no target

Aggregates:

- `expanded_step_count=3`
- `known_duration_s=1200`
- `total_duration_s=1200`
- `duration_total_complete=true`
- `known_distance_m=0`
- `total_distance_m=null`
- `distance_total_complete=false`

The approval authorized exactly one unscheduled Garmin workout creation. It did
not authorize scheduling, modification, deletion, device push, retry, or any
calendar change. This proposal contains no repeats, pace target, heart-rate
target, or Garmin JSON.

## The one approved live call

After explicit approval of that exact proposal, only this definition was
invoked:

```json
{
  "definition": {
    "name": "MCP TEST - Easy Run",
    "sport_type": "running",
    "steps": [
      {"step_type": "warmup", "duration": {"duration_type": "time", "duration_s": 300}},
      {"step_type": "run", "duration": {"duration_type": "time", "duration_s": 600}},
      {"step_type": "cooldown", "duration": {"duration_type": "time", "duration_s": 300}}
    ]
  },
  "confirmed": true
}
```

Do not display or save the serialized Garmin payload or raw response. Report
only the compact normalized tool result. If the call fails or is uncertain, do
not retry and do not delete or modify anything automatically.

## Manual Garmin Connect acceptance

- [x] Exactly one test workout exists.
- [x] Its name is `MCP TEST - Easy Run` and its sport is running.
- [x] Warmup, run, and cooldown appear in that order for 5, 10, and 5 minutes.
- [x] The workout opens normally.
- [x] It is not scheduled.
- [x] No duplicate or unexpected workout was created.
- [x] No calendar or device state changed.

The user confirmed every item passed. The test workout was not automatically
deleted. Deletion remains outside Milestone 8 and requires a separate explicit
request. Milestone 9 has not started.

---

# Historical Milestone 7 Offline Workout-Preview Verification

Milestone 7 was completed and manually verified on 2026-08-27 using only local
synthetic previews. No Garmin client/account operation occurred, no payload was
saved, and Milestone 8 was not started. No step below needs Garmin
authentication or a Garmin client.

## Safety and privacy boundary

Use only `garmin_preview_running_workout`. Do not invoke profile, activity,
recovery, workout-read, training-plan, upload, create, schedule, modify,
reschedule, unschedule, or delete operations. The preview tool has no Garmin
provider/client path and cannot affect an account, watch, or calendar.

Use only the synthetic definitions below. Do not substitute real workout names,
descriptions, dates, identifiers, account data, credentials, tokens, session
files, or Garmin payloads. Do not save the internal serialized Garmin payload;
the MCP tool intentionally does not return it.

## Semantics to verify

- `sport_type` is fixed to `running`.
- Executable `step_type` values are `warmup`, `run`, `recovery`, and `cooldown`;
  `repeat` contains `repeat_count` plus a non-empty nested `steps` sequence.
- Durations use exactly one of `duration_s`, `distance_m`, or open-ended with no
  measurement. Targets are omitted/no-target, an integer bpm range, or a pace
  range in seconds per kilometer.
- `expanded_steps` presents the actual repeated execution order with consecutive
  one-based `order` values.
- Known duration and distance subtotals are always explicit. A complete total is
  `null` when distance, time, or open steps make it indeterminate, and its
  completeness flag is false.
- Every successful response says `preview_only`, `uploaded=false`, and
  `scheduled=false`. It contains no Garmin enum IDs or full Garmin JSON.

## Synthetic preview calls

1. Simple time-based workout:

```json
{
  "definition": {
    "name": "Synthetic Time Preview",
    "steps": [
      {"step_type": "warmup", "duration": {"duration_type": "time", "duration_s": 300}},
      {"step_type": "run", "duration": {"duration_type": "time", "duration_s": 1200}},
      {"step_type": "cooldown", "duration": {"duration_type": "time", "duration_s": 300}}
    ]
  }
}
```

Confirm three expanded steps, `known_duration_s=1800`,
`total_duration_s=1800`, duration completeness true,
`known_distance_m=0`, `total_distance_m=null`, and distance completeness false.

2. Distance-based workout:

```json
{
  "definition": {
    "name": "Synthetic Distance Preview",
    "steps": [
      {"step_type": "warmup", "duration": {"duration_type": "distance", "distance_m": 1000}},
      {"step_type": "run", "duration": {"duration_type": "distance", "distance_m": 3000}},
      {"step_type": "cooldown", "duration": {"duration_type": "distance", "distance_m": 1000}}
    ]
  }
}
```

Confirm three expanded steps, `known_distance_m=5000`,
`total_distance_m=5000`, distance completeness true,
`known_duration_s=0`, `total_duration_s=null`, and duration completeness false.

3. Interval workout with repeats and both verified targets:

```json
{
  "definition": {
    "name": "Synthetic Interval Preview",
    "steps": [
      {"step_type": "warmup", "duration": {"duration_type": "time", "duration_s": 600}},
      {
        "step_type": "repeat",
        "repeat_count": 3,
        "steps": [
          {
            "step_type": "run",
            "duration": {"duration_type": "distance", "distance_m": 400},
            "target": {
              "target_type": "pace_range",
              "minimum_pace_s_per_km": 300,
              "maximum_pace_s_per_km": 330
            }
          },
          {
            "step_type": "recovery",
            "duration": {"duration_type": "time", "duration_s": 60},
            "target": {
              "target_type": "heart_rate_range",
              "minimum_heart_rate_bpm": 120,
              "maximum_heart_rate_bpm": 135
            }
          }
        ]
      },
      {"step_type": "cooldown", "duration": {"duration_type": "open"}}
    ]
  }
}
```

Confirm the expanded order is warmup, three alternating run/recovery pairs,
then cooldown. The expanded count is eight, known duration is 780 seconds,
known distance is 1200 meters, both complete totals are `null`, both
completeness flags are false, and both targets retain their public units.

4. Invalid definitions. Retry a small time preview once with `duration_s` set to
the string `"300"`, once with it set to the Boolean `true`, and once with an
unknown field. Confirm every call is rejected rather than coerced. Also confirm
an empty `steps` list, an inverted heart-rate or pace range, and an empty repeat
are rejected if the client makes those calls easy to enter.

## Acceptance

- [x] One simple time-based preview has correct normalized units and totals.
- [x] One distance-based preview has correct normalized units and totals.
- [x] One repeat preview has readable expanded step order and count.
- [x] Heart-rate bpm and pace seconds/km targets remain explicit and correct.
- [x] Known subtotals, complete totals, flags, and explicit `null` behavior are correct.
- [x] Invalid, coercible, conflicting, and unsupported definitions are rejected.
- [x] Responses contain no full Garmin payload or unrelated metadata.
- [x] Every response confirms no upload or scheduling occurred.
- [x] No Garmin upload, creation, scheduling, modification, unscheduling, or deletion occurred.
- [x] No private value or raw payload was saved to durable output.

The user confirmed this checklist passed. Milestone 7 is complete. Do not begin
Milestone 8 without a separate explicit request.

---

# Historical Milestone 6 Workout-Read Verification

Milestone 6 was completed and manually verified on 2026-08-27. The initial
private comparison exposed a saved-page/UI count mismatch and MCP Boolean
coercion. Strict Boolean validation and the current Garmin “My Workouts” query,
one-based pagination, filtering, and ordering semantics were then implemented
and successfully re-verified. No private values were recorded.

## Safety and privacy boundary

Use only these read-only tools:

- `garmin_workouts`
- `garmin_scheduled_workouts`

Do not invoke profile, activity, recovery, health, training-plan, upload,
create, schedule, modify, reschedule, unschedule, or delete operations. These
two tools cannot affect the Garmin watch or calendar.

Keep displayed workout values only in the local verification conversation. Do
not paste names, descriptions, dates, identifiers, calendar contents, account
data, or raw payloads into documentation, commits, tests, fixtures, issues,
logs, or summaries. Never inspect or display credentials, MFA codes, saved
tokens, or session files.

## Semantics to verify

- Saved pagination uses strict JSON integers: `start >= 0` and `limit` from 1
  through 100. Numeric strings are rejected.
- `running_only` is a strict JSON Boolean; strings and numbers are rejected.
  It uses Garmin's running query and a defensive normalized sport check.
  `source_count` is the filtered endpoint page size; `count` is the result after
  the defensive check.
- Scheduled dates use strict inclusive `YYYY-MM-DD` ranges of at most 31 days.
  Garmin supplies calendar dates, not instants. No timezone, offset, or
  time-of-day is inferred.
- Saved results follow Garmin's updated-date-descending “My Workouts” order.
  Scheduled results order by scheduled date, scheduled-workout ID, and workout
  ID.
- Declared fields are always present. Unavailable values are `null`.
- Duration uses `estimated_duration_s`; distance uses
  `estimated_distance_m`. No workout measurement is estimated.
- Raw steps, owner/account metadata, URLs, unrelated identifiers, and
  non-workout calendar items are absent.

## Verification checklist

1. Request one bounded page with `garmin_workouts(start=0, limit=20,
   running_only=false)`. Compare its template count and visible factual fields
   with Garmin Connect. Confirm the response contains only compact normalized
   fields and page metadata.

2. Request the same page with `running_only=true`. Confirm every returned item
   is a running workout and that both counts describe the filtered request. A
   defensive type mismatch may make `count` smaller than `source_count`.

3. Choose one recent or future inclusive range no longer than 31 days and call
   `garmin_scheduled_workouts`. Compare its scheduled-workout count and calendar
   dates with Garmin Connect. A range crossing one month boundary is useful for
   checking the provider's hidden month retrieval.

4. Inspect the declared normalized fields. Confirm unavailable name, sport,
   description, estimated duration, or estimated distance values appear as
   `null`, where observable, and no arbitrary Garmin payload fields appear.

5. If observable without changing Garmin, request a saved page beyond the end
   or a bounded calendar range with no scheduled workouts. Confirm `count` is
   zero and `items` is empty.

6. Confirm safe local rejection for invalid inputs: negative `start`, `limit`
   zero or greater than 100, non-boolean `running_only`, malformed/impossible
   dates, a reversed range, and a range longer than 31 inclusive days.

## Expected safe failures

- Invalid pagination and ranges are rejected before Garmin is called.
- Expired authentication, rate limits, malformed responses, and endpoint
  failures return concise secret-safe errors without raw upstream text.

Do not intentionally expire tokens, trigger rate limits, or induce endpoint
failures. Synthetic tests cover those paths.

## Acceptance

- [x] One bounded saved-workout page matches Garmin Connect.
- [x] Running-only endpoint filtering matches Garmin Connect.
- [x] One bounded scheduled-workout range matches Garmin Connect.
- [x] Normalized fields and explicit `null` behavior are correct.
- [x] Empty saved-workout or calendar results are correct where observable.
- [x] Invalid pagination and date ranges are rejected safely.
- [x] No unrelated read endpoint or any Garmin write/delete operation was used.
- [x] No private value or raw payload was saved to durable output.
