from __future__ import annotations

import tomllib
from pathlib import Path


def test_codex_garmin_mcp_config_is_safe_and_project_local() -> None:
    config = tomllib.loads(Path(".codex/config.toml").read_text())
    garmin = config["mcp_servers"]["garmin"]

    assert garmin["command"] == ".venv/bin/garminconnect-mcp"
    assert garmin["args"] == ["serve"]
    assert garmin["required"] is True
    assert garmin["default_tools_approval_mode"] == "prompt"
    assert "env" not in garmin
    assert "env_vars" not in garmin
    assert "cwd" not in garmin

    tools = garmin["tools"]
    assert tools == {
        "garmin_connection_status": {"approval_mode": "auto"},
        "garmin_ping": {"approval_mode": "auto"},
    }
