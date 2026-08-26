# Manual Milestone 7 Offline Workout-Preview Verification

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
