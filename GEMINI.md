# Gemini Project Instructions: garminconnect-mcp

This project is a local Model Context Protocol (MCP) server that exposes Garmin Connect data to AI agents (like Codex) using the `python-garminconnect` library.

## Project Overview

- **Purpose:** Provide a secure and summarized interface to Garmin Connect personal data.
- **Technologies:** Python 3.12+, `mcp` (FastMCP), `garminconnect`, `python-dotenv`.
- **Architecture:** 
  - `src/garminconnect_mcp/server.py`: Main entry point and tool definitions using `FastMCP`.
  - Uses `python-garminconnect` for unofficial API access.
  - Implements a caching client with MFA support.
  - Focuses on providing summarized data for workouts and activities to be more agent-friendly and privacy-conscious.

## Building and Running

### Setup
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
# Edit .env with GARMIN_EMAIL and GARMIN_PASSWORD
```

### Running
- **Initialize/Refresh Tokens:** Run `.venv/bin/garminconnect-mcp login` once interactively if MFA is required or to establish tokens.
- **MCP Server:** The server runs over stdio via the same command: `.venv/bin/garminconnect-mcp`.

### Testing & Quality
- **Tests:** `.venv/bin/python -m pytest`
- **Linting:** `.venv/bin/python -m ruff check .`
- **Formatting:** `.venv/bin/python -m ruff format .`
- **Privacy Scan:** `scripts/check-private-output.sh` (Requires `rg`)

## Development Conventions

### Privacy & Data Handling
- **Crucial:** Never log, print, or commit raw Garmin payloads (profile, health, activity, etc.) unless explicitly requested by the user.
- **Connectivity Checks:** Use `garmin_connection_status` or `garmin_ping` for smoke tests. Avoid using `garmin_profile` just to check if the connection works.
- **Summarization:** Prefer returning summarized, task-specific data (especially for workouts) instead of full Garmin JSON blobs.
- **Pre-commit:** Always run `scripts/check-private-output.sh` before committing any documentation, examples, or logs to ensure no private data (like weight, birthDate, or location) is leaked.

### Coding Style
- Follow PEP 8 (enforced by `ruff`).
- Use type hints (`from __future__ import annotations`).
- Tools are defined using the `@mcp.tool()` decorator in `server.py`.
- New tools should use `_call` or `_call_first` helpers to interact with the Garmin client.

### Testing
- Add unit tests in `tests/` for any new tools or logic.
- Use `pytest` and `monkeypatch` to mock the Garmin client (see `tests/test_server.py` for patterns).
