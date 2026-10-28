'''
Data model shared by every stage. Sources may vary; this does not.

JobRecord validates itself: each field has its own validator, and
JobRecord.from_raw() runs them all and then checks rules across fields.

Scope: a record is one finished attempt of a job, so its status is either
success or failed, and both timestamps are required.
'''
# builtins
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Self


class Status(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class InvalidRecord(ValueError):
    """A single record can't be used. It is skipped and counted, not fatal."""


@dataclass(frozen=True, slots=True)
class JobRecord:
    """One validated execution attempt of a job."""
    job_id: str
    status: Status
    started_at: datetime
    finished_at: datetime
    attempt: int

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @classmethod
    def from_raw(cls, raw: Any) -> Self:
        """Validate a raw record (e.g. a dict from JSON) and build a JobRecord, or raise InvalidRecord."""
        if not isinstance(raw, dict):
            raise InvalidRecord("not an object")

        try:
            record = cls(
                job_id=cls.validate_job_id(raw["job_id"]),
                status=cls.validate_status(raw["status"]),
                started_at=cls.validate_timestamp(raw["started_at"], "started_at"),
                finished_at=cls.validate_timestamp(raw["finished_at"], "finished_at"),
                attempt=cls.validate_attempt(raw["attempt"]),
            )
        except KeyError as e:
            raise InvalidRecord(f"missing field: {e.args[0]}") from None

        record.validate_order()
        return record

    # Field validators: each takes a raw value and returns a clean, typed one.

    @staticmethod
    def validate_job_id(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise InvalidRecord("invalid job_id")
        return value

    @staticmethod
    def validate_status(value: Any) -> Status:
        if not isinstance(value, str):
            raise InvalidRecord("invalid status")
        try:
            return Status(value.strip().lower())
        except ValueError:
            raise InvalidRecord("unknown status") from None

    @staticmethod
    def validate_attempt(value: Any) -> int:
        # bool is a subclass of int, so True would otherwise pass as attempt 1.
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidRecord("invalid attempt")
        return value

    @staticmethod
    def validate_timestamp(value: Any, field: str) -> datetime:
        """ISO 8601 string. Timestamps without a time zone are treated as UTC."""
        if not isinstance(value, str):
            raise InvalidRecord(f"invalid {field}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise InvalidRecord(f"invalid {field}") from None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    # Cross-field validation: rules that need more than one field.
    def validate_order(self) -> None:
        if self.finished_at < self.started_at:
            raise InvalidRecord("finished_at before started_at")
