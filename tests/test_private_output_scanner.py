from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path("scripts/check-private-output.sh")


def run_scanner(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), str(root)],
        check=False,
        text=True,
        capture_output=True,
    )


def test_private_output_scanner_allows_safe_status_output(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text('Smoke test result: {"ok": true}\n')

    result = run_scanner(tmp_path)

    assert result.returncode == 0
    assert "No private Garmin output patterns found." in result.stdout


def test_private_output_scanner_flags_raw_garmin_fields(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text('Raw profile: {"birthDate": "1994-10-16"}\n')

    result = run_scanner(tmp_path)

    assert result.returncode == 1
    assert "Potential private Garmin data found" in result.stderr
    assert "birthDate" in result.stderr


def test_private_output_scanner_ignores_test_fixtures(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "fixture.json"
    test_file.parent.mkdir()
    test_file.write_text('{"birthDate": "synthetic"}\n')

    result = run_scanner(tmp_path)

    assert result.returncode == 0
