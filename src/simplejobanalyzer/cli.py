'''
Command-line entry point: parse arguments, run the analyzer, print the summary.

    simplejobanalyzer examples/jobs.json
    simplejobanalyzer examples/jobs.json --out-format json
    simplejobanalyzer examples/jobs.json --in-format json_array
'''
# builtins
import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict

# modules
from simplejobanalyzer.analyzer import Summary, analyze
from simplejobanalyzer.sources import DataSource, DataSourceError, JsonArraySource


# Input formats: name -> DataSource class. A new format (e.g. JSON Lines) is one more entry.
# Each entry builds a source from the input path.
SOURCES: dict[str, Callable[[str], DataSource]] = {"json_array": JsonArraySource}

# Text output lists at most this many retried job ids; JSON output always lists all of them.
MAX_RETRIED_SHOWN = 10


def format_text(summary: Summary) -> str:
    average = summary.average_successful_duration_seconds
    retried = summary.jobs_with_retries

    shown = ", ".join(retried[:MAX_RETRIED_SHOWN])
    more = f" ... and {len(retried) - MAX_RETRIED_SHOWN} more" if len(retried) > MAX_RETRIED_SHOWN else ""

    return "\n".join([
        f"Total jobs:                     {summary.total_jobs}",
        f"Successful jobs:                {summary.successful_jobs}",
        f"Failed jobs:                    {summary.failed_jobs}",
        f"Average successful duration:    {f'{average:.2f}s' if average is not None else 'n/a'}",
        f"Jobs that required retries:     {len(retried)}" + (f" ({shown}{more})" if retried else ""),
        f"Invalid records (skipped):      {summary.invalid_records}",
    ])


def format_json(summary: Summary) -> str:
    return json.dumps(asdict(summary), indent=2)


FORMATTERS = {"text": format_text, "json": format_json}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simplejobanalyzer",
        description="Summarise job execution records from a JSON array file.",
    )
    parser.add_argument("path", help="file containing job records")
    parser.add_argument("--in-format", choices=list(SOURCES.keys()), default="json_array", help=f"input format (choices: {list(SOURCES.keys())})")
    parser.add_argument("--out-format", choices=list(FORMATTERS.keys()), default="text", help=f"output format (choices: {list(FORMATTERS.keys())})")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code: 0 on success, 1 if the input can't be read."""
    args = build_parser().parse_args(argv)
    try:
        source = SOURCES[args.in_format](args.path)
        summary = analyze(source.read())
    except DataSourceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(FORMATTERS[args.out_format](summary))
    return 0


def run() -> None:
    """Entry point for both `simplejobanalyzer` and `python -m simplejobanalyzer`: run and exit with main's code."""
    sys.exit(main())
