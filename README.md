# SimpleJobAnalyzer
A Very Basic Job Analyzer.

Reads job execution records from a JSON file, validates them and prints a summary.


Functional Requirements
---
- Read records from a JSON file.
- Validate the input and handle malformed records gracefully.
- Calculate execution duration for completed jobs.
- Produce a summary containing:
  - total jobs
  - successful jobs
  - failed jobs
  - average successful-job duration
  - jobs that required retries


How to run
---
Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                                      # install dependencies
uv run simplejobanalyzer examples/jobs.json                  # text summary
uv run simplejobanalyzer examples/jobs.json --out-format json
uv run pytest -q                                             # run the tests
```

Options:
- `--in-format` -> input format. Only `json_array` for now.
- `--out-format` -> `text` (default) or `json`.

Exit codes:
- `0` -> summary printed.
- `1` -> the file could not be read (missing file, not a JSON array, broken JSON).

Sample data:
- `examples/jobs.json` -> 100 records with a few invalid ones. Committed, so it runs out of the box.
- `scripts/generate_data.py` -> generates bigger files into `data/` (not committed):
  ```bash
  uv run python scripts/generate_data.py           # small (100), medium (50K), large (1M records)
  uv run python scripts/generate_data.py xlarge    # 5M records
  ```


Assumptions
---
1. A record is one finished attempt of a job.
   1. Status is either `success` or `failed`. Case does not matter (`SUCCESS` is fine).
   2. Both `started_at` and `finished_at` are required, and `finished_at` cannot be before `started_at`.
   3. Anything else (`queued`, `running`, unknown statuses) is invalid. See Extensibility.
2. A retry keeps the same `job_id` and increases `attempt`.
3. A job's final state is its latest attempt.
   1. If the same attempt shows up twice as both `success` and `failed`, `success` wins. This way the result does not depend on the order records arrive in.
   2. Side effect: if a job's newest attempt is still `running`, that record is invalid. The job is judged on its last finished attempt.
4. Timestamps are ISO 8601. Timestamps without a time zone are treated as UTC.
5. Summary:
   1. total jobs -> number of unique `job_id`s.
   2. successful jobs -> unique `job_id`s whose final state is `success`.
   3. failed jobs -> unique `job_id`s whose final state is `failed`.
      1. Every job is counted once, so successful + failed = total.
   4. average successful-job duration -> sum of the durations of the successful attempts / number of successful jobs.
      1. Only the attempt that succeeded counts. Time spent on earlier failed attempts is not included.
      2. If there are no successful jobs, it is `n/a` (`null` in JSON).
   5. jobs that required retries -> `job_id`s whose latest attempt is greater than 1.
      1. Text output shows the count and the first 10 ids. JSON output lists all of them.
6. Invalid records:
   1. A bad record (missing field, wrong type, bad timestamp, unknown status, not an object) is skipped and counted. It never stops the run.
   2. A bad file (missing, empty, not a JSON array, broken JSON) stops the run with exit code 1.
   3. An empty array `[]` is fine. It gives an all zero summary.


Design
---
```
JSON file -> Source -> raw records -> JobRecord (validation) -> JobAnalyzer (one entry per job_id) -> Summary -> CLI output
```

1. `sources/` -> where records come from.
   1. `DataSource` is the base class. It only has `read()`, which yields raw records one at a time.
   2. `JsonArraySource` reads a JSON array with `ijson`. It parses by JSON structure, not by lines, so pretty printed and minified files both work.
   3. The source does not know what a job is. It just reads.
2. `models.py` -> what a valid record is.
   1. `JobRecord.from_raw()` turns a raw dict into a `JobRecord` or raises `InvalidRecord`.
   2. Every field has its own validator. One more check across fields: `finished_at` >= `started_at`.
3. `analyzer.py` -> the counting.
   1. Keeps a dictionary: `job_id -> (attempt, status, duration)`.
   2. A newer attempt overwrites the entry. An older one is ignored. So every job has exactly one entry.
   3. The summary is calculated once at the end, from that dictionary.
4. `cli.py` -> arguments and output.
   1. `--in-format` and `--out-format` are just dictionaries of sources and formatters. No if/else chains.

Why this split:
- Each layer only does one thing, so each can change without touching the others.
- A new source, a new output format or a new rule touches one file.


Performance (not measured)
---
This has not been properly profiled. The points below are what we expect, not measured results.
1. Memory should stay low while reading, because `ijson` streams one record at a time.
2. Memory should grow with the number of unique jobs, not with the file size.
3. Streaming is probably a bit slower than loading the whole file with `json.load`, but should use far less memory.
4. To confirm any of this, the next step would be profiling with scalene on the generated files.


Known limitations
---
1. Memory grows with the number of unique jobs, not with the file size.
   1. Reading is streamed, but the analyzer keeps one small entry per `job_id`.
   2. Worst case, every record is a different job. Then the dictionary has as many entries as records.
   3. See Scaling for how to handle that.
2. We assume `ijson` uses its C backend (`yajl2_c`). Its pure python fallback is expected to be much slower. You can check with `python -c "import ijson; print(ijson.backend)"`.
3. Only JSON arrays are supported as input. Not JSON Lines.


Out of Scope
---
1. Fine tuning when to use full load vs lazy load.
   1. Right now we always stream with `ijson`.
   2. Small files could be loaded fully with `json.load`. We expect that to be faster for small files, but it holds the whole file in memory.
2. Reading from live, append only logs.
   1. Like Kafka -> reading from append only logs and tracking offsets.
   2. Would need JSON Lines, saving the byte offset after processing, and handling half written lines and log rotation.
3. Reasons for invalid records. Right now we only count them.
4. Parallel processing (see Scaling).


Scaling
---
1. Streaming vs full load.
   1. We stream files of all sizes. We assume that is a trade-off, not free.
   2. Streaming should use much less memory than `json.load`, but is probably a bit slower.
   3. We could pick a size threshold: small files -> `json.load`, big files -> stream. The right threshold would come from profiling.

2. Reading in parallel.
   1. Reading a local file is IO, but asyncio or thread pools do not really help with local files. Async makes sense if the data came over the network (db, http, S3 etc).
   2. Validation and counting are CPU bound. So async does not help here either. Neither do thread pools, because the GIL only lets one thread run python code at a time.
   3. With multiprocessing, we could split the records into batches and process them in parallel:
      1. The attempts of one job can land in different batches. So a batch cannot calculate the final counts on its own.
      2. What a batch can do is:
         1. de-duplicate -> a job_id will have exactly one entry in the batch.
         2. validate -> all invalid records get counted.
      3. Then we write the batch results into N partition files using hash partitioning: `zlib.crc32(job_id) % N`.
         1. We use crc32 and not python's `hash()`, because `hash()` for strings is randomised per process. The same job would go to different files.
         2. So the same job_id always goes to the same file.
      4. Now each partition file is small enough to load into memory. Since all attempts of a job are in the same file, we can find each job's final state and turn it into counts.
      5. Partitions have different jobs, so the counts from each partition just add up.
   4. In short:
      1. Phase 1: Split into batches -> each batch de-duplicates and validates -> write into partition files by `crc32(job_id) % N`.
      2. Phase 2: Read each partition -> count -> add up the counts.
   5. How many partitions?
      1. Ideally `N = ceil(unique_jobs * bytes per job / memory budget)`.
      2. The problem: we don't know the number of unique jobs in a file, and we don't know the bytes per job either.
      3. Bytes per job is a property of our code, not of the input. So we can measure it once, ahead of time (build a dictionary of fake entries and measure it with `tracemalloc`).
      4. For unique jobs, we can use an upper bound, an estimate, or not decide up front at all:
         1. Upper bound -> we do know the file size. Every record takes at least some minimum number of bytes, so `unique jobs <= records <= file size / smallest record size`. This over-estimates N, which is safe. Too many partitions is fine, too few is not.
         2. Sample -> read the first few thousand records, get the average record size and the ratio of unique job_ids, and scale that up to the file size. Cheap, but a sample can mislead (for example if retries only show up later in the file), so add a safety margin.
         3. HyperLogLog -> estimates the number of distinct job_ids in one extra pass, using only a few KB of memory.
         4. Don't decide up front -> pick a generous N (like 64). Extra partitions are cheap, just more files. If a partition still turns out too big in phase 2, split only that file again with a different hash (like `crc32(job_id + "salt") % M`).
      5. I would go with the last one. It works without knowing anything about the data in advance.

3. After that, we need to find the right batch size, number of workers and max batches running at a time.
   1. We can do this by profiling with scalene.
   2. Note: more workers only help as much as the part that runs in parallel. Parsing JSON still happens in one reader (Amdahl's Law).


Extensibility
---
1. What happens if new states like `queued`, `running` come in?
   1. Then `success` and `failed` are not the only valid states, and we cannot just overwrite by attempt anymore.
   2. `queued` and `running` won't have `finished_at`, so there is no duration for them.
   3. We would need a status rank: `queued` < `running` < `failed` / `success`. The same job can go queued -> running -> success/failed within the same attempt, and we can get them in any order. So we compare `(attempt, status rank)` instead of just `attempt`.
   4. The model validator would need to allow `finished_at` to be None for `running`, and both timestamps to be None for `queued`.
   5. The summary would get an "in progress" count.
2. New input format (JSON Lines, CSV, S3).
   1. Add a new `DataSource` subclass with a `read()` method.
   2. Add it to `SOURCES` in `cli.py`. That's it.
3. New output format.
   1. Add a function to `FORMATTERS` in `cli.py`.
4. New metric (like max duration).
   1. Add a field to `Summary` and calculate it in `JobAnalyzer.summary()`.


Testing
---
```bash
uv run pytest -q
```
- `test_json_array.py` -> reading files, pretty and minified, lazy reading, broken files.
- `test_models.py` -> validation of every field and the reasons for rejecting a record.
- `test_analyzer.py` -> de-duplication, retries, order not mattering, the summary.
- `test_cli.py` -> arguments, text and JSON output, exit codes.

The code also passes `mypy --strict`:
```bash
uv run --with mypy mypy --strict src tests
```


Time spent
---
- The core (source, model, analyzer, CLI, tests) took around ~2 hours.
- I spent extra time on purpose thinking about large files: streaming and the two phase design. That is beyond the brief.
