import json

import pytest

from simplejobanalyzer.sources import DataSourceError, JsonArraySource

RECORDS = [
    {"job_id": "a", "attempt": 1, "duration": 1.5},
    {"job_id": "b", "note": "has ]} and , inside"},
    None,
    "not an object",
]


@pytest.mark.parametrize("indent", [None, 2], ids=["minified", "pretty"])
def test_reads_every_record_in_order(tmp_path, indent):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(RECORDS, indent=indent))

    assert list(JsonArraySource(str(path)).read()) == RECORDS


def test_floats_stay_floats(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text('[{"duration": 1.5}]')

    record = next(JsonArraySource(str(path)).read())
    assert type(record["duration"]) is float


def test_empty_array(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("  [ ]  ")

    assert list(JsonArraySource(str(path)).read()) == []


def test_reads_lazily(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(RECORDS))

    records = JsonArraySource(str(path)).read()
    assert next(records) == RECORDS[0]   # first record available before the rest is read


@pytest.mark.parametrize(
    "text",
    ['{"job_id": "a"}', "[1, 2", "[1 2]", "[1,]", "[1] extra", ""],
    ids=["object", "truncated", "missing-comma", "trailing-comma", "trailing-data", "empty-file"],
)
def test_broken_files_raise(tmp_path, text):
    path = tmp_path / "jobs.json"
    path.write_text(text)

    with pytest.raises(DataSourceError):
        list(JsonArraySource(str(path)).read())


def test_missing_file_raises(tmp_path):
    with pytest.raises(DataSourceError):
        list(JsonArraySource(str(tmp_path / "nope.json")).read())
