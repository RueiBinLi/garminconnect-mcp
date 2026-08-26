# Manual Milestone 4 Recovery Verification

This checklist records verification of the read-only Milestone 4 recovery
implementation. The user confirmed all acceptance checks on 2026-08-26. No
Garmin write or delete operation was used.

## Safety and privacy boundary

Use only these tools:

- `garmin_daily_stats`
- `garmin_heart_rate`
- `garmin_sleep`
- `garmin_hrv`
- `garmin_hrv_range`
- `garmin_body_battery`
- `garmin_stress`

Do not invoke profile, activity, workout, scheduled-workout, training-plan, or
any Garmin write/delete tool. These seven recovery tools are read-only and
cannot change the watch.

Keep displayed health values only in the local verification conversation. Do
not paste them into documentation, commits, tests, fixtures, issues, logs, or
other durable files. Never display or inspect credentials, MFA codes, saved
tokens, session files, or the external token directory.

## Prerequisites

- Milestones 1 through 3 are complete.
- Saved-token authentication works without credential environment variables.
- Restart the local Codex client and create a new task so it discovers the new
  `garmin_hrv_range` tool and updated recovery schemas.
- Open Garmin Connect separately for visual comparison.

## Verification

1. Select one recent night that has sleep data. Ask Codex locally to call only
   `garmin_sleep` for its `YYYY-MM-DD` date. Compare the UTC start/end times,
   total sleep, deep/light/REM/awake/unmeasurable/nap durations, and Garmin sleep
   score/status. Durations must be seconds, and unavailable values must be
   `null`.

2. Select an inclusive date window containing the last three available HRV
   days. Ask Codex locally to call only `garmin_hrv_range`. Keep the window at 14
   days or fewer. Confirm the returned days and Garmin-supplied weekly average,
   last-night average, five-minute high, and status. Values must be milliseconds;
   Garmin days with no HRV summary may be omitted.

3. Ask Codex locally to call only `garmin_body_battery` for today's date. Compare
   charged, drained, highest, lowest, and latest values. They must use Garmin's
   native Body Battery scale. Confirm no sample timeline or event details are
   returned.

4. Select one date and ask Codex locally to call only `garmin_heart_rate` and
   `garmin_stress` for that date. Compare resting/minimum/maximum and seven-day
   average resting heart rate in bpm where Garmin supplies them. Compare average
   and maximum stress on Garmin's native scale. Confirm no per-sample chart data
   is returned.

5. For a field Garmin does not supply on one of the selected dates, confirm the
   normalized key remains present with `null`. Do not infer or calculate a
   replacement. An empty single-date response should retain the requested date
   and otherwise contain null fields; a missing HRV-range day may be absent.

`garmin_daily_stats` is also available for a factual compact daily summary in
meters, seconds, kcal, bpm, and Garmin-native stress/Body Battery units. Its
shape was covered by the live structural probe and synthetic tests; invoking it
is optional for the focused acceptance checklist.

## Expected safe failures

- Invalid or impossible dates are rejected before Garmin is called.
- HRV start dates after end dates are rejected.
- HRV ranges longer than 14 inclusive days are rejected.
- Expired authentication asks for a saved-login refresh without exposing
  upstream response text or secrets.
- Malformed responses, rate limits, and endpoint failures return concise,
  secret-safe categories without raw Garmin payloads.

Do not intentionally expire tokens or trigger rate limits merely to complete
manual acceptance; these paths are covered by synthetic tests.

## Acceptance checklist

- [x] Normalized sleep for one recent night matches Garmin Connect.
- [x] Normalized HRV for the last three available days matches Garmin Connect.
- [x] Today's normalized Body Battery matches Garmin Connect.
- [x] Normalized heart-rate and stress information for one selected date matches.
- [x] Unavailable fields are `null`, missing HRV days are omitted, and no values
      are estimated.
- [x] No profile, activity, workout, scheduled-workout, or training-plan data was
      requested.
- [x] No Garmin write or delete tool was invoked; the watch was unaffected.
- [x] No private health value, account data, credential, MFA code, token, session
      file, or raw payload was saved to the repository or another durable output.
- [x] `git status --short` contains only focused Milestone 4 source, test, and
      documentation changes.
