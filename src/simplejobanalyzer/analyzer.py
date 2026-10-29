'''
Turns a stream of raw records into a summary.

Reads records one at a time and keeps one entry per job_id in a dictionary:
the job's latest attempt. Retries of the same job overwrite its entry, so the
dictionary holds one entry per unique job (worst case: every job_id is unique).
The summary is counted once at the end, from each job's latest attempt.
'''
# builtins
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# modules
from simplejobanalyzer.models import InvalidRecord, JobRecord, Status

# What we keep per job: (attempt, status, duration_seconds).
# A small tuple instead of the whole JobRecord keeps memory per job low.
JobEntry = tuple[int, Status, float]


@dataclass(frozen=True, slots=True)
class Summary:
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    average_successful_duration_seconds: float | None
    jobs_with_retries: list[str]
    invalid_records: int


class JobAnalyzer:
    def __init__(self) -> None:
        self.jobs: dict[str, JobEntry] = {}
        self.invalid_records: int = 0

    def add(self, record: JobRecord) -> None:
        """
        Keep the record if it is the first we've seen for this job, or a newer attempt.
        """
        old: JobEntry | None = self.jobs.get(record.job_id)
        if old is None or self._is_newer(record, old):
            self.jobs[record.job_id] = (record.attempt, record.status, record.duration_seconds)

    def add_raw(self, raw: Any) -> None:
        """
        Validate a raw record and add it, or count it as invalid.
        """
        try:
            self.add(JobRecord.from_raw(raw))
        except InvalidRecord:
            self.invalid_records += 1

    def summary(self) -> Summary:
        successful = failed = 0
        duration_total = 0.0
        retried: list[str] = []

        for job_id, (attempt, status, duration) in self.jobs.items():
            # success or failure
            if status is Status.SUCCESS:
                successful += 1
                duration_total += duration
            else:
                failed += 1

            # retried
            if attempt > 1:
                retried.append(job_id)

        return Summary(
            total_jobs=len(self.jobs),
            successful_jobs=successful,
            failed_jobs=failed,
            average_successful_duration_seconds=duration_total / successful if successful else None,
            jobs_with_retries=sorted(retried),
            invalid_records=self.invalid_records,
        )

    @staticmethod
    def _is_newer(record: JobRecord, old: JobEntry) -> bool:
        old_attempt, old_status, _ = old
        if record.attempt != old_attempt:
            return record.attempt > old_attempt
        # Same attempt reported twice with different outcomes: prefer success,
        # so the result doesn't depend on the order records arrive in.
        return record.status is Status.SUCCESS and old_status is not Status.SUCCESS


def analyze(records: Iterable[Any]) -> Summary:
    """Analyze raw records from any source, e.g. analyze(JsonArraySource(path).read())."""
    analyzer = JobAnalyzer()
    for raw in records:
        analyzer.add_raw(raw)
    return analyzer.summary()
