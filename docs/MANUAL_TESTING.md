# Manual Milestone 5 Running-Summary Verification

The user completed this private local verification on 2026-08-26 and confirmed
that all observable cases passed. No Garmin write or delete operation was used.

## Safety and privacy boundary

Use only these read-only tools:

- `garmin_running_activities_by_date`
- `garmin_weekly_running_summary`
- `garmin_compare_running_weeks`
- `garmin_compare_recent_long_runs`

Do not invoke profile, recovery, workout, scheduled-workout, training-plan,
upload, create, schedule, modify, unschedule, or delete operations. These four
tools only read the running-activity date endpoint and cannot affect the watch.

Keep displayed activity values only in the local verification conversation. Do
not paste them into documentation, commits, tests, fixtures, issues, logs, or
other durable text. Never inspect or display credentials, MFA codes, saved
tokens, session files, or raw Garmin payloads.

## Semantics to verify

- Dates are strict `YYYY-MM-DD`, inclusive, ordered, and limited to 42 days.
- Measurements remain canonical: `distance_m`, `duration_s`,
  `pace_s_per_km`, heart rate in bpm, cadence in spm, and elevation gain in
  meters. Unavailable fields are `null`.
- Weeks run Monday through Sunday. Partial boundary weeks expose their clipped
  requested range.
- Distance and duration coverage give available/unavailable activity counts and
  a completeness flag. Known values may form a clearly marked partial sum;
  missing measurements are never treated as zero. A non-empty all-missing group
  returns `null`; an empty week returns zero.
- The range longest run uses greatest supplied distance. Recent “long runs” use
  the greatest supplied distance in each Monday-Sunday week across the end-date
  week and the requested one to four preceding weeks, newest candidate first.
  No effort classification or coaching interpretation is implied.

## Verification checklist

1. Choose one recent inclusive range no longer than 42 days and call
   `garmin_running_activities_by_date`. Compare its running activity dates,
   count, and available normalized measurements with Garmin Connect. Confirm
   non-running activities and raw payload fields are absent.

2. Call `garmin_weekly_running_summary` for a bounded range containing the week
   you want to inspect. Compare one week's distance in meters, duration in
   seconds, activity count, coverage, and identified longest measured-distance
   run with Garmin Connect.

3. Choose two adjacent Monday starts and call `garmin_compare_running_weeks`.
   Confirm both weekly facts and the signed distance, duration, and count
   changes. If a measurement is missing, confirm comparison completeness is
   false rather than silently treating it as zero.

4. Call `garmin_compare_recent_long_runs` with an end date and a preceding limit
   from 1 through 4. Confirm the latest candidate and preceding candidates are
   the greatest measured-distance run in each represented Monday-Sunday week.
   Confirm missing duration produces a `null` duration change.

5. Choose a valid bounded range with no running activities. Confirm the result
   is empty and weekly summaries, where requested, have zero count and totals.
   For any activity with an unavailable normalized field, confirm it remains
   `null` and coverage reports the missing measurement.

## Expected safe failures

- Invalid, impossible, reversed, or longer-than-42-day ranges are rejected
  before Garmin is called.
- Week comparison rejects non-Monday or non-adjacent starts.
- Recent long-run comparison rejects limits outside 1 through 4.
- Expired authentication, rate limits, malformed responses, and endpoint
  failures return concise secret-safe errors without raw upstream text.

Do not intentionally expire tokens or trigger rate limits. Synthetic tests cover
those paths.

## Acceptance

- [x] One recent bounded running range matches Garmin Connect.
- [x] One weekly distance, duration, and activity-count summary matches.
- [x] One adjacent week-over-week comparison matches.
- [x] The bounded range's longest run is correct.
- [x] The latest weekly longest-run comparison follows the documented rule.
- [x] Empty-range and unavailable-field behavior is correct.
- [x] No unrelated read endpoint or any Garmin write/delete operation was used.
- [x] No private value or raw payload was saved to durable output.
