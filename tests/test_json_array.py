import json
from pathlib import Path
from typing import Any

import pytest

from simplejobanalyzer.sources import DataSourceError, JsonArraySource

RECORDS: list[Any] = [
    {"job_id": "a", "attempt": 1, "duration": 1.5},
    {"job_id": "b", "note": "has ]} and , inside"},
    None,
    "not an object",
]


@pytest.mark.parametrize("indent", [None, 2], ids=["minified", "pretty"])
def test_reads_every_record_in_order(tmp_path: Path, indent: int | None) -> None:
    '''
    Both prettified json and non prettified json (line by line) should both work.
    Here we run the tests twice -> once prettified with indent=2 and once not prettified with
    no indent. Both should process all records.
    '''
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(RECORDS, indent=indent))

    assert list(JsonArraySource(str(path)).read()) == RECORDS


def test_empty_array(tmp_path: Path) -> None:
    '''
    Empty arrays should work just fine.
    '''
    path = tmp_path / "jobs.json"
    path.write_text("  [ ]  ")

    assert list(JsonArraySource(str(path)).read()) == []


def test_reads_lazily(tmp_path: Path) -> None:
    '''
    Generators load one at a time without loading everything in memory.
    '''
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(RECORDS))

    records = JsonArraySource(str(path)).read()
    assert next(records) == RECORDS[0]   # first record available before the rest is read


@pytest.mark.parametrize(
    "text",
    ['{"job_id": "a"}', "[1, 2", "[1 2]", "[1,]", "[1] extra", ""],
    ids=["object", "truncated", "missing-comma", "trailing-comma", "trailing-data", "empty-file"],
)
def test_broken_files_raise(tmp_path: Path, text: str) -> None:
    '''
    Test all invalid cases.
    '''
    path = tmp_path / "jobs.json"
    path.write_text(text)

    with pytest.raises(DataSourceError):
        list(JsonArraySource(str(path)).read())


def test_missing_file_raises(tmp_path: Path) -> None:
    '''
    Missing file raises error.
    '''
    with pytest.raises(DataSourceError):
        list(JsonArraySource(str(tmp_path / "nope.json")).read())
