# Garmin MCP Agent Guidance

## Privacy Defaults

- Treat Garmin Connect responses as private health/account data.
- Do not print raw Garmin profile, sleep, HRV, heart-rate, stress, Body Battery,
  activity, or user settings payloads unless the user explicitly asks for those
  raw fields.
- Use `garmin_connection_status` or `garmin_ping` for smoke tests. Do not use
  `garmin_profile` as a connectivity check.
- Prefer summarized, task-specific outputs for training analysis instead of raw
  JSON payloads.
- Before committing docs, scripts, examples, or copied output, run:

```bash
scripts/check-private-output.sh
```

