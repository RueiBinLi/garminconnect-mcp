#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

PATTERN='("?(birthDate|weight|height|latitude|longitude|userName|userData|userSleep|vo2MaxRunning|vo2MaxCycling|lactateThreshold(Speed|HeartRate)?|activityId)"?[[:space:]]*[:=])'

if ! command -v rg >/dev/null 2>&1; then
  echo "error: rg is required for private Garmin data scanning" >&2
  exit 2
fi

matches="$(
  rg --line-number --ignore-case --glob '*.md' --glob '*.txt' --glob '*.json' \
    --glob '*.jsonl' --glob '*.http' --glob '*.sh' --glob '*.toml' \
    --glob '!scripts/check-private-output.sh' --glob '!**/tests/**' \
    --glob '!.git/**' --glob '!.venv/**' --glob '!**/__pycache__/**' \
    --glob '!*.egg-info/**' --glob '!.pytest_cache/**' --glob '!.ruff_cache/**' \
    "$PATTERN" "$ROOT" || true
)"

if [[ -n "$matches" ]]; then
  cat >&2 <<'EOF'
Potential private Garmin data found in durable output surfaces.

Do not keep raw Garmin profile, health, activity, or account payloads in docs,
scripts, examples, or other durable text. Replace the payload with a safe
summary, synthetic fixture, or a connection-only result such as {"ok": true}.

Matches:
EOF
  echo "$matches" >&2
  exit 1
fi

echo "No private Garmin output patterns found."
