# Manual Milestone 3 Activity Verification

This guide records verification of the read-only Milestone 3 activity
implementation. The user confirmed all acceptance checks on 2026-08-26. No
Garmin write operation was used.

## Safety and privacy boundary

Use only these tools:

- `garmin_recent_activities`
- `garmin_activity`

Do not invoke profile, health, sleep, HRV, Body Battery, stress, recovery, or
workout tools. Do not create, schedule, modify, unschedule, or delete anything.
The two allowed tools are read-only and cannot affect the watch.

Keep displayed activity values only in the local verification conversation. Do
not paste them into documentation, commits, tests, fixtures, issues, logs, or
other durable files. Never display or inspect credentials, MFA codes, saved
tokens, session files, or the external token directory.

## Prerequisites

- Milestones 1 and 2 are complete.
- Saved-token authentication works without credential environment variables.
- The local Codex client has been restarted so it sees the updated activity tool
  signatures.
- Garmin Connect is open separately for visual comparison.

## Verification

1. Ask Codex:

   ```text
   Use only garmin_recent_activities with start 0, limit 5, and running_only
   false. Show the normalized result. Do not call any other Garmin tool.
   ```

   Confirm exactly five or the available smaller count is returned. Compare the
   name, date/time, type, distance, duration, pace, heart rate, cadence, and
   elevation values with Garmin Connect. Units must be meters, seconds, seconds
   per kilometer, bpm, spm, and meters respectively.

2. Ask Codex:

   ```text
   Use only garmin_recent_activities with start 0, limit 5, and running_only
   true. Show the normalized result. Do not call any other Garmin tool.
   ```

   Confirm every returned item is a run in Garmin Connect. This page is the five
   most recent running activities, not merely the running subset of the previous
   all-activity page.

3. Choose one activity ID from the running-only result, then ask Codex locally:

   ```text
   Use only garmin_activity for the selected recent run ID. Show the normalized
   result. Do not call any other Garmin tool.
   ```

   Insert the selected ID through the tool UI or local prompt without copying it
   into a tracked file. Confirm the returned activity ID matches the selection
   and compare every available normalized field with Garmin Connect.

4. In any result where Garmin did not supply a normalized field, confirm the key
   is still present with `null`. Confirm Codex does not estimate a missing metric.
   In particular, pace must remain `null` when Garmin does not supply average
   speed.

## Expected safe failures

- `start` below zero is rejected.
- `limit` outside 1 through 100 is rejected before Garmin is called.
- A nonnumeric or nonpositive activity ID is rejected before Garmin is called.
- An unknown numeric activity ID reports that the activity was not found.
- Expired authentication asks for saved-login refresh without exposing upstream
  response text or secrets.
- Malformed responses and endpoint/rate-limit failures return concise categories
  without raw Garmin payloads.

Do not intentionally expire tokens or probe unknown IDs merely to complete the
main acceptance checklist; these failure paths are covered by synthetic tests.

## Acceptance checklist

- [x] Latest five normalized activities match Garmin Connect.
- [x] Running-only filtering returns only runs and matches Garmin Connect order.
- [x] One selected recent run's normalized details match Garmin Connect.
- [x] Unavailable Garmin fields are present as `null` and are not estimated.
- [x] No profile, health, sleep, HRV, Body Battery, stress, recovery, or workout
      data was requested.
- [x] No Garmin write or delete tool was invoked.
- [x] No private activity value, account data, credential, MFA code, token, or
      session file was saved to the repository or another durable output.
- [x] `git status --short` contains only the focused Milestone 3 source, test, and
      documentation changes.

Canonical response fields use meters and seconds for unambiguous calculations.
Clients may display distance in kilometers and pace as `MM:SS/km` without
changing the normalized schema.
