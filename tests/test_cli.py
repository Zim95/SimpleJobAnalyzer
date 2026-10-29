import json
from pathlib import Path
from typing import Any

import pytest

from simplejobanalyzer.cli import main

RECORDS: list[Any] = [
    {"job_id": "a", "status": "success", "started_at": "2026-10-28T10:00:00Z", "finished_at": "2026-10-28T10:05:00Z", "attempt": 1},
    {"job_id": "b", "status": "failed", "started_at": "2026-10-28T10:00:00Z", "finished_at": "2026-10-28T10:01:00Z", "attempt": 1},
    {"job_id": "b", "status": "success", "started_at": "2026-10-28T10:02:00Z", "finished_at": "2026-10-28T10:12:00Z", "attempt": 2},
    "not an object",
]


@pytest.fixture
def jobs_file(tmp_path: Path) -> str:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(RECORDS, indent=2))
    return str(path)


def test_text_output(jobs_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([jobs_file]) == 0

    out = capsys.readouterr().out
    assert "Total jobs:                     2" in out
    assert "Successful jobs:                2" in out
    assert "Average successful duration:    450.00s" in out
    assert "Jobs that required retries:     1 (b)" in out
    assert "Invalid records (skipped):      1" in out


def test_json_output(jobs_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([jobs_file, "--out-format", "json"]) == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary == {
        "total_jobs": 2,
        "successful_jobs": 2,
        "failed_jobs": 0,
        "average_successful_duration_seconds": 450.0,
        "jobs_with_retries": ["b"],
        "invalid_records": 1,
    }


def test_missing_file_exits_with_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "nope.json")]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err


def test_broken_file_exits_with_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "broken.json"
    path.write_text("[1, 2")

    assert main([str(path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_no_successful_jobs_shows_na(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([RECORDS[1]]))

    main([str(path)])
    assert "Average successful duration:    n/a" in capsys.readouterr().out


def test_in_format_json_array(jobs_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([jobs_file, "--in-format", "json_array"]) == 0
    assert "Total jobs:                     2" in capsys.readouterr().out


def test_unknown_in_format_is_rejected(jobs_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([jobs_file, "--in-format", "csv"])

    assert exit_info.value.code == 2          # argparse's exit code for bad arguments
    assert "invalid choice" in capsys.readouterr().err
