'''
Tests for the analyzer: de-duplication by job_id and the summary built from it.

Records are plain dicts here (no files), except for the one end-to-end test.
'''
import json
from pathlib import Path
from typing import Any

from simplejobanalyzer.analyzer import analyze
from simplejobanalyzer.sources import JsonArraySource


def rec(
    job_id: str,
    status: str,
    attempt: int,
    start: str = "2026-10-28T10:00:00Z",
    finish: str = "2026-10-28T10:05:00Z",
) -> dict[str, Any]:
    """
    Build one raw record (a dict, as the source would yield it).
    Defaults to a 5-minute run.
    """
    return {
        "job_id": job_id,
        "status": status,
        "started_at": start,
        "finished_at": finish,
        "attempt": attempt
    }


RECORDS: list[Any] = [
    rec("a", "success", 1),                                  # 300 s
    rec("b", "failed", 1),
    rec("b", "success", 2, finish="2026-10-28T10:10:00Z"),   # retried, then 600 s
    rec("c", "failed", 1),
    rec("c", "failed", 2),                                   # retried, still failed
    rec("d", "failed", 1),
]


def test_summary() -> None:
    """
    Every summary field is correct for a small mix of single runs, retries and failures.
    """
    summary = analyze(RECORDS)

    assert summary.total_jobs == 4
    assert summary.successful_jobs == 2              # a, and b on its retry
    assert summary.failed_jobs == 2                  # c, d
    assert summary.average_successful_duration_seconds == 450   # (300 + 600) / 2
    assert summary.jobs_with_retries == ["b", "c"]
    assert summary.invalid_records == 0


def test_successful_and_failed_add_up_to_total() -> None:
    """Each job is counted once, by its final state, so successful + failed == total."""
    summary = analyze(RECORDS)

    assert summary.successful_jobs + summary.failed_jobs == summary.total_jobs


def test_order_does_not_matter() -> None:
    """The summary is the same whatever order the records arrive in."""
    assert analyze(RECORDS[::-1]) == analyze(RECORDS)


def test_older_attempt_arriving_late_is_ignored() -> None:
    """An older attempt read after a newer one does not replace it; the job still counts as retried."""
    summary = analyze([rec("b", "success", 2), rec("b", "failed", 1)])

    assert summary.successful_jobs == 1
    assert summary.failed_jobs == 0
    assert summary.jobs_with_retries == ["b"]


def test_same_attempt_success_and_failed_prefers_success_in_any_order() -> None:
    """If the same attempt is reported as both success and failed, success wins, in either order."""
    records = [rec("z", "failed", 1), rec("z", "success", 1)]

    assert analyze(records).successful_jobs == 1
    assert analyze(records[::-1]).successful_jobs == 1


def test_invalid_records_are_counted_and_skipped() -> None:
    """Invalid records (out-of-scope status, non-objects, None) are counted, not treated as jobs."""
    summary = analyze([rec("a", "success", 1), rec("x", "running", 1), "not an object", None])

    assert summary.total_jobs == 1
    assert summary.invalid_records == 3


def test_no_successful_jobs_gives_no_average() -> None:
    """With no successful jobs the average is None instead of dividing by zero."""
    assert analyze([rec("x", "failed", 1)]).average_successful_duration_seconds is None


def test_empty_input() -> None:
    """No records gives an all-zero summary with no average and no retries."""
    summary = analyze([])

    assert summary.total_jobs == 0
    assert summary.jobs_with_retries == []
    assert summary.average_successful_duration_seconds is None


def test_end_to_end_with_json_file(tmp_path: Path) -> None:
    """A real JSON file read by JsonArraySource produces the same totals, plus its invalid record."""
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(RECORDS + ["bad"], indent=2))

    summary = analyze(JsonArraySource(str(path)).read())

    assert summary.total_jobs == 4
    assert summary.invalid_records == 1
