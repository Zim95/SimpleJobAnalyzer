"""Generate sample job-record files of different sizes for testing and profiling.

Usage:
    python scripts/generate_data.py                 # small, medium, large
    python scripts/generate_data.py xlarge          # just the extra-large file
    python scripts/generate_data.py --seed 7 small  # different random data

Files are written to data/ (git-ignored). Each file is a JSON array. The small file is
pretty-printed; larger files put one record per line inside the array so they stay
readable with `head` but are still a single JSON array, not JSON Lines.

About 5% of records are invalid in assorted ways, so validation paths get exercised.
Records are written one at a time, so generating a large file uses little memory.
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# name -> (record count, writer). Writers are defined below.
SIZES = {
    "small": (100, "pretty"),
    "medium": (50_000, "one_per_line"),
    "large": (1_000_000, "one_per_line"),
    "xlarge": (5_000_000, "one_per_line"),
}
DEFAULT_SIZES = ["small", "medium", "large"]
INVALID_RATE = 0.05
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


IST = timezone(timedelta(hours=5, minutes=30))

# Mix "Z", explicit offsets and naive timestamps, as real inputs often do.
# name -> (weight, formatter)
TIMESTAMP_FORMATS = {
    "utc_z": (70, lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
    "offset": (20, lambda dt: dt.astimezone(IST).isoformat()),
    "naive": (10, lambda dt: dt.replace(tzinfo=None).isoformat()),
}


def _iso(dt: datetime, rng: random.Random) -> str:
    weights, formatters = zip(*TIMESTAMP_FORMATS.values())
    return rng.choices(formatters, weights=weights)[0](dt)


def _attempts_for_job(job_id: str, rng: random.Random) -> list[dict]:
    """1-3 attempts; earlier attempts fail, the last one succeeds, fails or is running."""
    n_attempts = rng.choices([1, 2, 3], weights=[80, 15, 5])[0]
    start = BASE_TIME + timedelta(seconds=rng.randint(0, 30 * 24 * 3600))
    records = []
    for attempt in range(1, n_attempts + 1):
        duration = timedelta(seconds=rng.randint(5, 3600))
        is_last = attempt == n_attempts
        status = rng.choices(["success", "failed", "running"], weights=[85, 12, 3])[0] if is_last else "failed"
        if rng.random() < 0.05:
            status = status.upper()
        finished = None if status.lower() == "running" else _iso(start + duration, rng)
        records.append({
            "job_id": job_id,
            "status": status,
            "started_at": _iso(start, rng),
            "finished_at": finished,
            "attempt": attempt,
        })
        start = start + duration + timedelta(seconds=rng.randint(1, 120))
    return records


def _drop_random_field(record: dict, rng: random.Random) -> dict:
    dropped = rng.choice(list(record))
    return {k: v for k, v in record.items() if k != dropped}


# Ways to corrupt a valid record: name -> function(record, rng) returning the bad record.
CORRUPTIONS = {
    "missing_field": _drop_random_field,
    "unknown_status": lambda r, rng: {**r, "status": "done"},
    "bad_timestamp": lambda r, rng: {**r, "started_at": "yesterday"},
    "finished_before_started": lambda r, rng: {**r, "finished_at": "2025-01-01T00:00:00Z"},
    "attempt_below_one": lambda r, rng: {**r, "attempt": 0},
    "attempt_wrong_type": lambda r, rng: {**r, "attempt": "two"},
    "job_id_wrong_type": lambda r, rng: {**r, "job_id": 12345},
    "success_without_finish": lambda r, rng: {**r, "status": "success", "finished_at": None},
    "not_an_object": lambda r, rng: "not an object",
    "null": lambda r, rng: None,
}


def _make_invalid(record: dict, rng: random.Random):
    """Return a corrupted copy of a valid record (or a non-object)."""
    corrupt = rng.choice(list(CORRUPTIONS.values()))
    return corrupt(record, rng)


def iter_records(count: int, rng: random.Random):
    """Yield `count` records: mostly valid job attempts, ~5% invalid."""
    produced = 0
    job_number = 0
    while produced < count:
        job_number += 1
        for record in _attempts_for_job(f"job-{job_number:08d}", rng):
            if produced >= count:
                return
            yield _make_invalid(record, rng) if rng.random() < INVALID_RATE else record
            produced += 1


def _write_pretty(f, records) -> None:
    json.dump(list(records), f, indent=2)
    f.write("\n")


def _write_one_per_line(f, records) -> None:
    """A JSON array with one record per line, written one record at a time."""
    f.write("[\n")
    separator = ""
    for record in records:
        f.write(separator + json.dumps(record, separators=(",", ":")))
        separator = ",\n"
    f.write("\n]\n")


def write_file(name: str, seed: int) -> Path:
    rng = random.Random(seed)
    count, writer_name = SIZES[name]
    writer = WRITERS[writer_name]
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"jobs_{name}.json"
    with path.open("w", encoding="utf-8") as f:
        writer(f, iter_records(count, rng))
    return path


WRITERS = {"pretty": _write_pretty, "one_per_line": _write_one_per_line}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sizes", nargs="*", choices=list(SIZES), help="which files to build (default: small medium large)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    for name in args.sizes or DEFAULT_SIZES:
        path = write_file(name, args.seed)
        print(f"{name:7} {SIZES[name][0]:>10,} records  {path.stat().st_size / 1_048_576:8.1f} MB  {path}")


if __name__ == "__main__":
    main()
