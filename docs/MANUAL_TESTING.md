# Manual Milestone 6 Workout-Read Verification

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
