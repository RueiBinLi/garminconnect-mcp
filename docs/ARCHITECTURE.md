# Garmin Connect MCP — Architecture and Upstream Audit

## Milestone history and current scope

This document records the repository as audited on 2026-08-25. Milestone 0
changes documentation only; it does not add or change MCP behavior.

Milestone 3 introduced the first Garmin provider/normalization boundary for
read-only activities. Milestone 4 extended that boundary to recovery data and
was manually verified. Milestone 5 adds deterministic running aggregation over
normalized activities and was manually verified on 2026-08-26. Milestone 6
adds read-only saved-workout and scheduled-workout boundaries and was manually
verified on 2026-08-27. Milestone 7 adds an offline-only validated running-
workout builder, deterministic Garmin serializer, and safe preview tool. Its
offline preview behavior was manually verified on 2026-08-27. Milestone 8 adds
a confirmation-gated, exactly-one upload boundary for validated running
workouts. One explicitly approved synthetic creation and manual Garmin
verification passed on 2026-08-27. Scheduling is not part of this milestone.
Milestone 9 adds separately gated scheduling and unscheduling boundaries for one
existing assignment. Exactly one existing test workout was scheduled and later
unscheduled after separate exact approvals; both manual Garmin checks passed on
2026-08-27. The template remained intact and private assignment values were not
recorded.
Milestone 10 adds an offline proposal and confirmation-gated composition for
creating exactly one new validated running workout and scheduling only that
newly returned workout ID on one date. One exact synthetic workflow and its
manual Garmin verification passed on 2026-08-27; private identifiers were not
recorded.
Milestone 11 adds a read-only weekly running-proposal application service,
strict desired-session constraints, and normalized configured running Zone 2
reads. Offline verification and one manually accepted live proposal passed on
2026-08-27 without a Garmin write or retained private value.
Milestone 12 adds a process-local, expiring, one-use approval boundary around
that exact proposal and sequentially composes the existing safe Milestone 10
provider operation. Offline synthetic verification and one exact, separately
approved live workflow passed on 2026-08-27. The user confirmed all creations
and assignments, absence of duplicates, preservation of existing items, and no
unrelated changes. Private live values were not retained.
The subsequent naming extension adds strict half-marathon plan identity and a
Monday plan anchor. The anchor week is `W01`; later proposal weeks derive their
one-based two-digit week deterministically and cannot precede the anchor.

## Repository structure

```text
garminconnect-mcp/
├── src/garminconnect_mcp/server.py  # Authentication, MCP tools, CLI
├── src/garminconnect_mcp/provider.py # Garmin activity/recovery/workout providers and safe errors
├── src/garminconnect_mcp/activities.py # Pure activity normalization and schema
├── src/garminconnect_mcp/heart_rate_zones.py # Pure zone normalization
├── src/garminconnect_mcp/training.py # Pure weekly and long-run aggregation
├── src/garminconnect_mcp/planner.py # Strict deterministic weekly proposal service
├── src/garminconnect_mcp/weekly_scheduler.py # One-use weekly approval and execution
├── src/garminconnect_mcp/recovery.py # Pure recovery normalization and schemas
├── src/garminconnect_mcp/workouts.py # Pure workout normalization and schemas
├── src/garminconnect_mcp/workout_builder.py # Strict pre-write model, aggregation, and serializer
├── tests/test_server.py             # Synthetic unit tests with a fake Garmin client
├── tests/test_provider.py           # Synthetic activity provider/error tests
├── tests/test_activities.py         # Synthetic activity normalization tests
├── tests/test_heart_rate_zones.py   # Synthetic zone/provider tests
├── tests/test_training.py           # Synthetic running aggregation tests
├── tests/test_planner.py            # Synthetic weekly proposal and safety tests
├── tests/test_weekly_scheduler.py   # Approval, stale-state, and partial-write tests
├── tests/test_recovery.py           # Synthetic recovery normalization tests
├── tests/test_recovery_provider.py  # Synthetic recovery provider/error tests
├── tests/test_workouts.py           # Synthetic workout normalization tests
├── tests/test_workout_provider.py   # Synthetic workout provider/error tests
├── tests/test_workout_builder.py    # Synthetic builder/preview/serialization tests
├── tests/test_private_output_scanner.py
├── scripts/check-private-output.sh  # Durable-text privacy scanner
├── docs/                            # Client setup, specification, and roadmap
├── pyproject.toml                   # Package metadata and dependencies
├── .env.example                     # Local credential configuration template
└── .gitignore                       # Local secret/build/cache exclusions
```

The implementation remains intentionally small. Activity, recovery, workout
reads, and validated workout creation have provider seams; other runtime
behavior still lives in `server.py`. `training.py` performs factual aggregation
only; there is no coaching or planning module. `workout_builder.py` is a pure
offline boundary and cannot obtain a Garmin client.

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

Activity, recovery, workout-read, and validated-creation MCP tools no longer
depend on Garmin response keys or exception text. The legacy workout write
tools are unchanged; they still call the third-party client directly and retain
their existing summary behavior.

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

## Recorded-lap and aerobic-drift boundary

`garmin_activity_splits` reads `get_activity_splits()` and normalizes only
`lapDTOs`. Its `split_type` is `lap`: Auto Lap, manual, interval, mile-based, and
partial laps remain recorded laps and are never relabeled as kilometers. Pace
uses Garmin `averageMovingSpeed` only. The public fields use meters, seconds,
seconds per kilometer, bpm, and spm; missing measurements are `null`.

`garmin_activity_aerobic_drift` requests `get_activity_details()` with
`maxchart=1000` and `maxpoly=0`. Garmin can downsample long activities. Metric
positions are resolved from `metricDescriptors`; fixed indexes are forbidden.
Raw samples and polylines remain inside the provider/analysis boundary.

## Activity temperature and weather-station boundary

The two temperature-related sources are intentionally separate:

```text
get_activity_details()
  -> descriptor-resolved directAirTemperature samples
  -> arithmetic Celsius summary
  -> garmin_activity_temperature

get_activity_weather()
  -> historical weather-station response
  -> compact observation with unverified temperature/wind units
  -> garmin_activity_weather
```

`garmin_activity_temperature` requests at most 10,000 chart samples with no
polyline. The installed detail parser resolves `directAirTemperature` through
`metricDescriptors`; fixed indexes are not used. Missing, non-numeric, Boolean,
and non-finite samples are discarded. The public result contains only the
arithmetic mean, minimum, maximum, valid count, source, and warnings. These
device/activity readings are Celsius but can be affected by device placement,
body heat, sunlight, and local exposure.

`garmin_activity_weather` uses the unofficial activity-weather method as a
historical weather-station observation. It preserves a valid ISO 8601
offset-bearing `issueDate` as `observed_at`, but does not reinterpret the
timezone. Relative humidity is explicitly percent. Temperature and wind units
remain unverified, so their names are deliberately unit-neutral and
`units_verified` is false. Coordinates, station name, raw station/type objects,
and all other raw fields are discarded; only condition description,
station-present state, and station timezone survive normalization.

The pure analyzer removes stationary segments from the running halves while
retaining them as validity evidence, divides accumulated usable distance in
half, and proportionally splits a segment that crosses the midpoint. Half HR is
trapezoidally time-weighted and half speed is distance divided by included time:

```text
efficiency = average_speed_m_per_s / average_hr_bpm
decoupling_pct =
    (first_half_efficiency - second_half_efficiency)
    / first_half_efficiency
    * 100
```

Positive decoupling means second-half efficiency worsened. Positive HR change
means higher HR, positive speed change means faster speed, and positive pace
change means slower pace. Duration, distance, sample coverage, stops,
walk/stand typed splits, interval-like lap intensity, half-pace difference, and
elevation evidence determine `usable_for_drift_analysis`. Minimums are 1,200
usable seconds, 3,000 usable meters, and 20 valid samples. A stop or walk/stand
section is substantial at 60 seconds and 5% of elapsed time. Half pace may
differ by at most 10%; strongly uneven elevation means at least 60 meters of
range and 20 meters climbed per kilometer. Warnings preserve factual metrics
without adding medical or coaching interpretation.

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

## Milestone 6 workout-read boundary

The installed `garminconnect` dependency exposes a legacy saved-workout
offset/limit wrapper and scheduled workouts as a zero-indexed calendar-month
endpoint. Garmin's current web UI adds filtering, ordering, and one-based start
semantics that the dependency wrapper does not expose. The public MCP contract
keeps those quirks behind `GarminWorkoutProvider`:

```text
Two narrow read-only MCP tools
    │ validated page or inclusive range
    ▼
GarminWorkoutProvider
    │ saved page, or only intersecting calendar months
    ▼
Known list/workouts/calendarItems envelopes
    │ non-workout calendar entries discarded immediately
    ▼
Pure workout normalizers
    │ compact explicit-unit schema; null unavailable fields
    ▼
Deterministically ordered MCP response
```

`garmin_workouts` accepts a zero-based offset and a page size from 1 through
100. The provider converts the public offset to Garmin's one-based `start`, sets
`myWorkoutsOnly=true`, excludes ATP/shared-only modes, and requests Garmin's
updated-date-descending UI order. This matters because the unfiltered legacy
request can return a service entry absent from all rendered Garmin workout tabs.
`running_only=true` sends Garmin's `sportTypeKey=running` filter and repeats an
exact normalized running check at the boundary. `source_count` reports the
filtered endpoint page size and `count` reports items remaining after that
defensive check. The MCP boundary uses Pydantic's strict integer and Boolean
adapters so coercible lookalikes are rejected before a provider call.

`garmin_scheduled_workouts` accepts strict inclusive dates spanning at most 31
days. The provider fetches one or, for a cross-month range, two intersecting
calendar months, retains only entries with a schedule identifier and embedded
workout, then filters to the requested dates. Results sort by scheduled date,
scheduled-workout ID, and workout ID. The endpoint supplies a Garmin
`calendarDate` in `YYYY-MM-DD`; this is a calendar label, not an instant. No UTC
offset, local zone, or time-of-day is inferred. A scheduled entry without a
usable date cannot be placed in a bounded range and is omitted; malformed
non-date values are rejected.

Both schemas retain only `workout_id`, `name`, `sport_type`, `description`,
`estimated_duration_s`, and `estimated_distance_m`; scheduled results add
`scheduled_workout_id` and `scheduled_date`. Absent declared fields are `null`.
The normalizers discard owner/account metadata, internal URLs, unrelated IDs,
timestamps of uncertain semantics, arbitrary calendar entries, and nested step
payloads. No step count is exposed because the list/calendar endpoints have not
yet been verified to supply a stable summary count.

Only known direct-list, `workouts`, `scheduledWorkouts`, and `calendarItems`
envelopes are accepted. Empty known lists return empty results. Wrong container
types, invalid dates, authentication failures, rate limits, not-found/month
endpoint failures, and other connection failures map to bounded secret-safe
errors. The provider invokes only the read-only workout-list request and
`get_scheduled_workouts`; no upload, create, schedule, modify, unschedule, or
delete method participates.

## Milestone 7 offline workout-builder boundary

Milestone 7 introduces no Garmin provider or write connection. The installed
`garminconnect 0.3.11` typed-workout source verifies the running sport, warmup,
interval, recovery, cooldown, repeat, time, distance, lap-button, no-target,
heart-rate, and pace classifications and their DTO structure. Public client
behavior additionally verifies that custom target bounds belong beside
`targetType` on an executable step. The builder supports only those mappings.

```text
garmin_preview_running_workout(definition)
    │ strict Pydantic validation; unknown fields and coercion rejected
    ▼
Canonical WorkoutDefinition / WorkoutStep model
    │ seconds, meters, bpm, and seconds per kilometer only
    ▼
Pure expansion and aggregation
    │ known subtotals, complete totals/nulls, readable execution order
    ├──────────────────────────────┐
    ▼                              ▼
Compact MCP preview          Internal Garmin serializer
no Garmin JSON               deterministic DTO structure
no client/network            not connected to upload/schedule
```

`WorkoutDefinition` fixes `sport_type` to `running`; allows a one-to-80-
character name and optional one-to-500-character description without control
or surrounding whitespace; and requires a non-empty step list. Executable
steps have exactly one time, distance, or open duration and at most one target.
Targets are limited to no target, a custom integer bpm range, or a custom
seconds-per-kilometer pace range. Repeat groups require two through 50
iterations and a non-empty sequence.

Safety limits allow at most two repeat levels, 100 structural steps, 100
expanded executable steps, 86,400 seconds or 100,000 meters per step, 604,800
known expanded seconds, and 1,000,000 known expanded meters. Inputs must be
finite positive JSON numbers within their field ranges; JSON Booleans and
numeric strings are not accepted. Heart-rate and pace bounds must increase in
their public unit. Repeat groups cannot carry durations or targets.

Aggregation expands repeats deterministically. `known_duration_s` and
`known_distance_m` sum only explicit measurements. `total_duration_s` is
present only when every expanded step is time-ended; `total_distance_m` is
present only when every expanded step is distance-ended. Otherwise the
corresponding total is `null` and its completeness flag is false. Open steps
therefore leave both totals incomplete.

The serializer owns all Garmin IDs and undocumented key names. It converts
pace seconds per kilometer to meters per second only on the wire, keeps custom
target values at executable-step level, assigns deterministic preorder step
numbers, and serializes repeat groups recursively. Its result is callable only
inside Python and is never returned by MCP. The preview exposes only normalized
input, expanded order, aggregates, and compact classification/count diagnostics,
plus explicit `uploaded=false` and `scheduled=false` state.

## Milestone 8 validated creation boundary

```text
garmin_create_running_workout(definition, confirmed=false)
    │ exact Milestone 7 strict validation happens first
    ├── false/omitted ──► compact no-write result; no client construction
    │
    └── true
          │ deterministic Milestone 7 serializer output only
          ▼
    GarminWorkoutProvider.create_running_workout
          │ one upload_workout call; no retry
          ▼
    compact normalized created result
          │ workout ID + validated facts only
          └── scheduled=false; no calendar/device operation
```

FastMCP requires `confirmed` to be a strict JSON Boolean. The tool also checks
the type for direct Python calls. The whole `WorkoutDefinition` is validated
before `_workout_provider()` can obtain the cached Garmin client. A false or
omitted confirmation returns `created=false` and directs the caller back to the
preview. A true confirmation crosses the provider boundary once.

The provider alone can see the deterministic Garmin payload and raw upload
response. It calls only `upload_workout`; it has no automatic retry,
verification read, rollback, scheduling, modification, unscheduling, deletion,
or device-push step. If the result is malformed or lacks a usable workout ID,
the error is reported without trying to repair or delete the possibly created
template. The caller must manually inspect Garmin before deciding what to do.

Successful output contains only creation state, the normalized workout ID, the
validated name and fixed running sport, complete duration/distance totals when
available, `scheduled=false`, and an unscheduled message. Raw requests and
responses, account/owner fields, URLs, response-provided names, and unrelated
identifiers are discarded. Authentication, rate-limit, endpoint, unsupported-
client, malformed-response, and missing-ID failures use stable secret-safe
errors.

## Milestone 9 existing-workout calendar boundary

```text
garmin_preview_workout_schedule(workout_id, scheduled_date)
    └── strict full request validation; offline compact proposal

garmin_schedule_existing_workout(..., confirmed=false)
    ├── false/omitted ──► offline no-write result; no client construction
    └── true
          │ normalized same-date scheduled-workout read
          ├── exact duplicate ──► compact idempotent result; no write
          └── absent ──► one guarded schedule call ──► compact identity

garmin_unschedule_existing_workout(scheduled_workout_id, confirmed=false)
    ├── false/omitted ──► one read-only lookup and exact compact proposal
    └── true
          │ repeat exact read-only lookup
          └── one guarded unschedule call; workout_deleted=false
```

The three MCP argument models require ASCII positive-decimal identifier strings,
strict date strings, and strict JSON Booleans, and advertise/reject additional
properties. Validation happens before a client can be obtained. The scheduling
preview and false/omitted scheduling path are entirely offline. The unscheduling
preview intentionally performs one read so it identifies the exact assignment
instead of trusting caller-supplied workout/date facts.

Confirmed scheduling reuses the Milestone 6 normalized scheduled-range boundary
for an exact same-workout/same-date duplicate check. A duplicate returns its
existing scheduled-workout ID and makes no schedule call. Otherwise the provider
calls only `schedule_workout` once and requires a usable assignment ID. Any
returned workout ID or date must match the validated request when present.
Malformed, missing-ID, or mismatched write results are uncertain because Garmin
may have changed the calendar; the server stops and directs manual inspection
before any retry.

Confirmed unscheduling uses the installed read-only
`get_scheduled_workout_by_id` method and the existing pure normalizer immediately
before one `unschedule_workout` call. Output retains only the assignment ID,
workout ID, calendar date, `workout_deleted=false`, and a status message. The
provider has no template-delete, update, upload, clone, rollback, cleanup, or
device-push call in either Milestone 9 path.

Installed `garminconnect 0.3.11` source shows that schedule/unschedule call the
low-level POST/DELETE methods directly and do not use the library's transient
retry decorator. Its low-level request implementation can normally refresh and
replay once after HTTP 401. After each preceding safe read, the provider holds a
write guard and temporarily replaces only that refresh hook with a fail-closed
authentication error. A Milestone 9 write therefore makes at most one HTTP
attempt even on that dependency replay path. The hook is restored immediately.
Network ambiguity maps to an explicit uncertain-result error; the provider
never retries or verifies by repeating a write.

`scheduled_date` remains Garmin's date-only calendar label. The server infers no
time, timezone, offset, or instant. It never directly pushes an assignment to a
device, although Garmin may subsequently synchronize calendar state through its
normal service behavior.

## Milestone 10 combined create-and-schedule boundary

```text
garmin_preview_create_and_schedule_running_workout(definition, date)
    └── strict full validation and normalized offline proposal

garmin_create_and_schedule_running_workout(..., confirmed=false)
    ├── false/omitted ──► same offline proposal; no client/network
    └── true
          │ one guarded serializer-produced upload
          │ validate exactly one returned workout ID
          ▼
       normalized exact same-ID/date duplicate read
          ├── exact assignment ──► compact result; no schedule write
          └── absent ──► one guarded schedule call
```

The MCP model accepts one strict `WorkoutDefinition`, one strict date string,
and one strict Boolean only. It has no field for an existing workout ID, raw
Garmin JSON, account data, URL, timestamp, timezone, or batch. Unknown fields
and coercion are rejected. Definition expansion, safety totals, serialization,
date validation, and confirmation validation all complete before a client can
be constructed.

Only the provider sees the upload payload and raw write responses. It validates
the upload response into one positive numeric ID and supplies only that ID to
the Milestone 9 duplicate/schedule boundary. Successful output is limited to
creation/schedule state, known IDs, requested date, validated name/sport and
complete totals, `partial_failure`, and a status message. There is no response-
provided name, owner/account field, URL, token, device identifier, raw payload,
calendar body, or unrelated ID.

Both upload and schedule use the single-attempt guard. If upload is uncertain,
execution stops before any calendar read or write. If creation is safely known
but duplicate checking or scheduling fails or becomes uncertain, the provider
returns compact `partial_failure=true` state and preserves the new unscheduled
workout. It never retries, verifies by repeating a write, rolls back, deletes,
unschedules, cleans up, modifies, clones, or calls a device-push method.

Garmin exposes no stable workout-creation idempotency key and this local server
has no database. The workflow therefore cannot guarantee creation deduplication
after an uncertain upload. Manual Garmin inspection is mandatory before any new
proposal or action; the uncertain invocation must never be replayed.

## Milestone 11 weekly proposal boundary

The public interface is
`garmin_weekly_running_proposal(week_start, constraints)`. FastMCP and the
application service validate the complete strict request before any provider
factory can obtain the cached Garmin client. The planner receives only three
read interfaces:

```text
strict request
    -> 28-day normalized running-activity read
    -> 7-day normalized HRV read
    -> 7-day normalized scheduled-workout read
    -> configured running/default heart-rate-zone read
    -> pure deterministic proposal construction
    -> strict WorkoutDefinition validation and aggregation
    -> compact proposal-only response
```

No interface supplied to the planner contains an upload, creation, scheduling,
modification, unscheduling, deletion, retry, cleanup, rollback, cloning, or
device-push method. The service cannot call the legacy write tools. Scheduled
commitments lose both private identifier fields and descriptions before they
enter the result.

The activity lookback is exactly the four complete Monday-Sunday weeks before
the requested week (28 inclusive days). HRV coverage is the final seven days of
that lookback. Scheduled-workout coverage is exactly the requested week. Hard-
session classification is explicitly unavailable because the existing compact
activity boundary contains measurements but no validated effort-category fact.

The zone provider invokes the dependency's dedicated
`get_heart_rate_zones()` read. It accepts only Garmin's running or default sport
profile, validates five strictly increasing floors and the configured maximum,
and derives contiguous inclusive bpm ranges. Running wins over default. The
planner uses only Zone 2's exact lower and upper bpm bounds for each main run
step; warmup and cooldown remain untargeted. Raw biometric responses, account
settings, device fields, and unrelated sport profiles cannot cross the
normalizer.

The deterministic policy requires at least two non-empty weeks with complete
distance coverage. It uses the rounded median distance and floored median run
count as baselines. Two or more normalized HRV statuses in the explicit
`low`/`unbalanced`/`poor` set multiply new distance by 0.90; an optional cap is
applied next. Existing running commitments consume date and count capacity. A
new long run receives 100% with one new session, 60% with two, or 40% with
three or more; the rest is divided across easy runs. Each distance-only
definition has ordered 10% untargeted warmup, 80% configured Zone 2 run, and
10% untargeted cooldown steps. `desired_sessions` replaces the historical
session baseline when supplied, while `maximum_sessions` remains a hard cap.
Every numeric intermediate is
returned under `rule_calculations`; the policy is a product rule, not medical or
scientific advice.

Workout naming is a pure planning concern. `half_marathon` maps to the fixed
public code `HM`; arbitrary plan codes are rejected. Names use
`HM WNN - Purpose Distance`, where distance is the complete workout total in
kilometers and retains a necessary decimal. This keeps Garmin Connect readable
without using private identifiers or relying on calendar state.

## Milestone 12 weekly approval and execution boundary

Milestone 12 exposes a two-phase interface:

```text
garmin_preview_weekly_running_plan(week_start, constraints)
    -> strict Milestone 11 validation and normalized reads
    -> exact deterministic proposal and intended write order
    -> SHA-256 fingerprint + opaque 15-minute approval token
    -> process-local bounded approval store

garmin_schedule_weekly_running_plan(token, fingerprint, confirmed=false)
    -> false: offline lookup and no-write state
    -> true: atomically consume one approval
       -> recompute fingerprint
       -> revalidate every definition, date, purpose, order, and aggregate
       -> reread only the normalized Monday-Sunday calendar
       -> stop on stale state or an exact-date conflict
       -> for each approved session in ascending date/order:
          create_and_schedule_running_workout(definition, exact_date)
       -> stop immediately on known or uncertain failure
```

The deterministic fingerprint hashes canonical ASCII JSON containing the whole
reviewed Milestone 11 response plus the exact ordered intended writes. The token
is random, URL-safe, held only in process memory, capped at 32 pending approvals,
expires after 15 minutes, and is consumed by one confirmed invocation. The
client cannot submit or alter a proposal. A server restart, expiry, mismatched
fingerprint, prior use, different preview, or different week cannot authorize a
write.

The approval store privately retains the normalized calendar identifiers needed
to detect replacement of an otherwise similar commitment. Those identifiers are
never hashed into public approval material, persisted, logged, or returned.
Before the first write, the fresh normalized calendar snapshot must exactly
equal the preview snapshot. Any difference makes the proposal stale; a newly
occupied approved date is the narrower conflict case. The service never picks
another date or changes an existing assignment.

The only weekly write dependency is the existing Milestone 10 provider method.
For each session it deterministically serializes one validated definition,
uploads at most once, performs the existing duplicate calendar read for only
the returned new workout ID and exact date, and schedules at most once. The
weekly service does not call legacy tools. It cannot modify, unschedule, delete,
clone, clean up, roll back, retry, or push to a device.

Execution is sequential and is not a transaction. A failure preserves all
earlier successful sessions. A scheduling failure preserves the current new
unscheduled workout. Later sessions are not attempted. Malformed or uncertain
creation results are treated as uncertain because Garmin may have accepted the
write before returning an unusable response. Garmin has no stable creation
idempotency key, so uncertain creation cannot be deduplicated safely. The one-use
approval is never replayed; manual Garmin inspection is mandatory.

The compact execution result reports only the week, proposal fingerprint,
requested/completed counts, per-session public facts and aggregates, safe state,
partial/uncertain flags, remaining not-attempted count, and next action. Workout
IDs, schedule IDs, approval tokens, raw Garmin data, serialized payloads,
endpoint names, URLs, account/profile fields, device identifiers, and upstream
exception text do not cross the boundary.

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
    │ lists 32 MCP tools without contacting Garmin
    │ invokes only an explicitly selected tool
    ▼
Saved-token Garmin client
```

Neither configuration contains Garmin credentials, tokens, MFA values, or a
repository-local token path. The untracked host configuration stores the
absolute executable path and `serve` argument; authentication keeps using the
external default token directory. All 36 tools remain discoverable so future
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
| `garminconnect` | `==0.3.11` | Audited unofficial Garmin Connect authentication and API client |
| `mcp` | `>=1.2.0,<2` | FastMCP server and stdio transport |
| `pydantic` | `>=2.11,<3` | Strict MCP pagination and Boolean input validation |
| `python-dotenv` | `>=1.0.1` | Load local credentials and settings from `.env` |

The Milestone 1 environment resolved `garminconnect 0.3.11`, `mcp 1.29.1`, and
`python-dotenv 1.2.3`.

Milestone 9 narrows the Garmin dependency to the audited installed version. Its
single-attempt write guarantee depends on the verified 0.3.11 schedule wrapper
and low-level authentication-refresh path; accepting an unaudited patch release
would silently weaken that safety claim. A future dependency update must repeat
the source audit and replay-guard tests before changing this pin.

Milestone 0 found a dependency compatibility defect: a fresh install resolved
`mcp 2.1.0`, which no longer provides `mcp.server.fastmcp`. Milestone 1 fixes the
reproducibility issue with the minimal compatible upper bound, `mcp<2`. A
deliberate MCP 2.x migration remains a possible later change.

## Existing MCP tools

The server exposes 36 tools.

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
| `garmin_activity_temperature` | Read, normalized/private | Returns arithmetic mean/minimum/maximum Celsius device-recorded temperature without the sample series | Implemented; manual verification pending |
| `garmin_activity_weather` | Read, normalized/private | Returns a compact historical weather-station observation with unverified temperature/wind units and no coordinates or station name | Implemented; manual verification pending |
| `garmin_running_activities_by_date` | Read, normalized/private | Returns running activities for an inclusive range of at most 42 days | Milestone 5 complete |
| `garmin_weekly_running_summary` | Read, aggregate/private | Returns weekly meter/second/count facts, coverage, and longest runs | Milestone 5 complete |
| `garmin_compare_running_weeks` | Read, aggregate/private | Compares adjacent Monday-Sunday weeks with absolute deltas and coverage | Milestone 5 complete |
| `garmin_compare_recent_long_runs` | Read, aggregate/private | Compares weekly greatest-distance candidates across at most five weeks | Milestone 5 complete |
| `garmin_workouts` | Read, normalized/private | Returns one bounded page with Garmin running-only filtering, a defensive normalized check, and explicit units/nulls | Milestone 6 complete |
| `garmin_scheduled_workouts` | Read, normalized/private | Returns scheduled workouts for an inclusive range of at most 31 calendar days | Milestone 6 complete |
| `garmin_preview_running_workout` | Offline pre-write | Strictly validates, expands, and aggregates a running-workout definition without a Garmin client or full serialized payload | Milestone 7 complete |
| `garmin_create_running_workout` | Confirmation-gated write | Validates first; false/omitted confirmation makes no client call, while true uploads exactly one serializer-produced running workout and never schedules it | Milestone 8 complete and manually verified |
| `garmin_preview_workout_schedule` | Offline pre-write | Strictly validates one existing workout ID and one date without constructing a client | Milestone 9 complete |
| `garmin_schedule_existing_workout` | Confirmation-gated write | False/omitted confirmation is offline; true checks an exact duplicate then schedules at most once with compact output | Milestone 9 complete and manually verified |
| `garmin_unschedule_existing_workout` | Read/confirmation-gated delete | False/omitted confirmation reads one normalized assignment; true re-reads then removes only that assignment once | Milestone 9 complete and manually verified |
| `garmin_preview_create_and_schedule_running_workout` | Offline pre-write | Strictly validates one definition and one date and returns normalized execution order, aggregates, and no-write warnings | Milestone 10 complete |
| `garmin_create_and_schedule_running_workout` | Confirmation-gated write | False/omitted is offline; true uploads once and schedules only the returned new ID at most once, preserving compact partial state | Milestone 10 complete and manually verified |
| `garmin_weekly_running_proposal` | Read, normalized/private | Reuses bounded normalized facts and deterministic rules to return strict proposed sessions without writes | Milestone 11 complete and manually verified |
| `garmin_preview_weekly_running_plan` | Read-only approval preview | Reuses Milestone 11 and adds exact intended writes, deterministic fingerprint, and an opaque expiring approval token | Milestone 12 complete and manually verified |
| `garmin_schedule_weekly_running_plan` | One-use confirmation-gated write | False is offline; true revalidates, checks stale calendar state, and sequentially composes only the safe Milestone 10 boundary | Milestone 12 complete and manually verified |
| `garmin_schedule_workout` | Write | Schedules an existing template and summarizes the result | Partial FR-12; no local date validation or duplicate protection |
| `garmin_create_scheduled_workout` | Write | Uploads arbitrary Garmin JSON, then schedules it | Partial FR-11/FR-13; no internal schema, validation, rollback, or duplicate protection |
| `garmin_unschedule_workout` | Write/destructive | Removes a calendar assignment by scheduled-workout ID | Basic FR-14 behavior exists |

The three legacy write tools remain immediately callable and unchanged. They do
not inherit Milestone 8/9 confirmation and normalization guarantees and must not
be used for those verification workflows.

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

Milestone 6 adds synthetic tests for compact workout schemas, explicit nulls,
saved-page bounds, UI-equivalent My Workouts and running filters, known response envelopes,
non-workout calendar-item removal, cross-month range retrieval, inclusive
31-day limits, deterministic ordering, empty results, malformed responses,
authentication failures, rate limits, endpoint failures, strict MCP Boolean
validation, orphan exclusion, and MCP wrappers. At completion, the suite
contains 143 passing tests.

Milestone 7 adds synthetic tests for every supported step, duration, and target;
mixed and nested repeats; deterministic step ordering and serialization;
explicit-unit previews; complete and incomplete aggregates; strict rejection of
unknown, coercible, Boolean, non-finite, conflicting, inverted, unsupported, and
oversized inputs; exact boundary acceptance; safe structural diagnostics; and
offline MCP calls. Client-construction and write-method reachability are guarded
by tests. At the manual-verification stopping point, the full suite contains
234 passing tests.

Milestone 8 adds synthetic provider and MCP tests for false/omitted
confirmation, strict Boolean intent, validation-before-client construction,
arbitrary-payload rejection, exact deterministic serialization, one-call/no-
retry behavior, compact privacy-filtered results, malformed and missing-ID
responses, secret-safe failure mapping, unsupported client behavior, and the
absence of scheduling, modification, unscheduling, deletion, rollback, and
device-push reachability. All automated paths remain offline.
At completion, the full suite contains 263 passing tests. One explicitly
approved synthetic creation and the manual Garmin acceptance checklist passed
without recording its private identifier or raw response.

Milestone 9 adds offline synthetic coverage for strict IDs/dates/Booleans and
unknown fields, validation before client construction, offline preview/default
scheduling, exact duplicate idempotency, one-call scheduling and unscheduling,
read-only assignment lookup, compact privacy filtering, safe error categories,
uncertain-result stopping, unavailable client behavior, unreachable unrelated
writes, and the dependency HTTP-401 replay guard. Live Garmin writes are never
part of the automated suite. At the pre-live-verification stopping point, the
full suite contains 317 passing tests.

Milestone 10 adds offline synthetic coverage for strict combined input,
validation-before-client construction, offline preview/default confirmation,
one guarded upload, returned-ID-only scheduling, exact duplicate detection,
compact partial failures, uncertain stopping, privacy filtering, unreachable
cleanup/device operations, and upload plus schedule HTTP-replay guards. Live
Garmin writes are not part of the automated suite. One separately approved live
workflow and its manual acceptance checklist passed without retaining private
identifiers or raw response data.

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
| FR-09 Existing workouts | Milestone 6 complete | The provider matches the current UI's `myWorkoutsOnly`, one-based pagination, sport filtering, and ordering semantics; live count and running-filter comparisons passed. |
| FR-10 Scheduled workouts | Milestone 6 complete | Inclusive ranges up to 31 calendar days hide Garmin's month endpoint and preserve verified date-only semantics; live comparison passed. |
| FR-11 Create running workout | Milestone 8 complete | The strict schema and serializer connect to one confirmation-gated upload with compact output and no retry or scheduling path. One explicitly approved synthetic creation and manual Garmin verification passed. |
| FR-12 Schedule workout | Milestone 9 complete | The strict preview/confirmation boundary, exact duplicate protection, compact normalization, single-attempt guard, and date-only semantics passed one approved live assignment and manual verification. |
| FR-13 Create and schedule | Milestone 10 complete | A strict offline proposal and confirmed provider composition upload once, schedule only the returned ID at most once, and preserve explicit partial state without cleanup. One approved workflow passed manual verification; creation deduplication remains impossible after an uncertain upload. |
| FR-14 Unschedule workout | Milestone 9 complete | The separate read-preview/confirmation boundary removed the verified assignment once after separate approval; manual verification confirmed the template remained intact. |
| Training summaries | Milestone 5 complete | Bounded running retrieval, weekly aggregates with coverage, longest-run selection, and week comparisons were manually verified without coaching interpretation. |
| Weekly planner | Implemented | Deterministic proposals include strict plan anchoring, desired/maximum sessions, configured Zone 2, and transparent aggregates. |
| Provider boundary | Partial | Activity, recovery, workout reads, validated creation, and safe existing-workout calendar operations have provider seams; profile and legacy workout writes still directly depend on the Garmin client. |
| Normalized domain models | Partial | Activities, recovery data, workout reads, and pre-write running definitions use compact schemas; profile, connected writes, and later planning domains do not. |
| Error handling | Partial | Activity, recovery, workout-read, validated-creation, and Milestone 9 failures use stable secret-safe categories; profile and legacy write families still propagate third-party errors. |
| Write safety | Partial | Validated creation and Milestone 9 operations require separate strict confirmation and at-most-once provider calls and passed live verification; legacy writes still lack these guarantees. |
| Local-first/single-user | Implemented by design | The stdio process, local `.env`, and local token directory fit the target. |
| Offline testability | Partial | Activity, recovery, training-summary, workout-read, builder, validated-creation, and safe calendar boundaries are covered with synthetic data; legacy writes and planning remain outside that coverage. |

## Recommended milestone sequence

The repository already has useful Garmin authentication and endpoint coverage, so
it should be extended rather than rewritten. The roadmap order remains suitable:

1. Authentication and token reuse were verified in Milestone 1.
2. MCP discovery and connection were verified in Milestone 2.
3. Activity normalization and its provider seam were completed and manually
   verified in Milestone 3.
4. Recovery normalization and manual Garmin comparison completed Milestone 4.
5. Milestone 5 running summaries were implemented and manually verified.
6. Milestone 6 workout reads were implemented and manually verified on
   2026-08-27.
7. Milestone 7 workout building, serialization, and offline preview were
   implemented and manually verified on 2026-08-27.
8. Milestone 8 validated creation, one explicitly approved synthetic upload,
   and manual Garmin verification completed on 2026-08-27.
9. Milestone 9 safe scheduling/unscheduling, separate approvals, and manual
   Garmin verification completed on 2026-08-27.
10. Milestone 10's combined boundary, offline tests, one exact approved workflow,
    and manual Garmin verification completed on 2026-08-27. Milestone 11 has not
    started.

The MCP dependency incompatibility was resolved in Milestone 1 with an upper
bound rather than a framework migration.
