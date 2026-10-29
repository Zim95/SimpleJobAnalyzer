from datetime import datetime, timezone
from typing import Any

import pytest

from simplejobanalyzer.models import InvalidRecord, JobRecord, Status


def make(**overrides: Any) -> dict[str, Any]:
    record = {
        "job_id": "job-1",
        "status": "success",
        "started_at": "2026-10-28T10:00:00Z",
        "finished_at": "2026-10-28T10:05:00Z",
        "attempt": 1,
    }
    record.update(overrides)
    return record


def test_valid_record() -> None:
    '''
    Valid record.
    '''
    job = JobRecord.from_raw(make())

    assert job.job_id == "job-1"
    assert job.status is Status.SUCCESS
    assert job.attempt == 1
    assert job.duration_seconds == 300


def test_failed_is_valid() -> None:
    '''
    Failed is a valid state.
    '''
    assert JobRecord.from_raw(make(status="failed")).status is Status.FAILED


def test_status_is_case_insensitive() -> None:
    '''
    Status is case insensitive.
    '''
    assert JobRecord.from_raw(make(status=" SUCCESS ")).status is Status.SUCCESS


def test_naive_timestamp_is_treated_as_utc() -> None:
    '''
    Timestamp strings are converted to datetime.
    '''
    job = JobRecord.from_raw(
        make(started_at="2026-10-28T10:00:00", finished_at="2026-10-28T10:01:00")
    )
    assert job.started_at == datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)


def test_mixed_offsets_compare_correctly() -> None:
    '''
    Duration is calculated correctly.
    '''
    # 15:30 at +05:30 is 10:00 UTC, so this ran for 60 seconds.
    job = JobRecord.from_raw(
        make(started_at="2026-10-28T15:30:00+05:30", finished_at="2026-10-28T10:01:00Z")
    )
    assert job.duration_seconds == 60


def test_missing_field_is_reported_by_name() -> None:
    '''
    Missing field test
    '''
    record = make()
    del record["attempt"]

    with pytest.raises(InvalidRecord, match="missing field: attempt"):
        JobRecord.from_raw(record)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("not a dict", "not an object"),
        (None, "not an object"),
        (make(job_id=42), "invalid job_id"),
        (make(job_id="  "), "invalid job_id"),
        (make(status=7), "invalid status"),
        (make(status="done"), "unknown status"),
        (make(status="running"), "unknown status"),      # out of scope: only success / failed
        (make(attempt=0), "invalid attempt"),
        (make(attempt="2"), "invalid attempt"),
        (make(attempt=True), "invalid attempt"),
        (make(started_at="yesterday"), "invalid started_at"),
        (make(started_at=None), "invalid started_at"),
        (make(finished_at=None), "invalid finished_at"),
        (make(finished_at="2026-10-28T09:00:00Z"), "finished_at before started_at"),
    ],
)
def test_invalid_records(raw: Any, reason: str) -> None:
    '''
    Some invalid job record types.
    '''
    with pytest.raises(InvalidRecord, match=reason):
        JobRecord.from_raw(raw)


def test_records_are_immutable() -> None:
    '''
    Once we have a job record, we cannot make changes to it.
    '''
    job = JobRecord.from_raw(make())

    with pytest.raises(AttributeError):
        job.attempt = 2  # type: ignore[misc]  # deliberately breaking immutability
