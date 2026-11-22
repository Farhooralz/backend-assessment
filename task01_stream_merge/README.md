# Task 1: Merging payment event streams

`merge(streams)` takes up to 64 single-use iterators of `(time, id, amount)` events, each sorted by
`(time, id)`, and returns one lazy, sorted, de-duplicated iterator. Standard library only.

## Run

```bash
cd task01_stream_merge
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python measure_memory.py          # memory measurement
```

```python
from stream_merge import merge

list(merge([iter([(1, "A", 7), (3, "C", 4)]), iter([(1, "A", 7), (2, "B", 5)])]))
# [(1, 'A', 7), (2, 'B', 5), (3, 'C', 4)]
```

## Test

```bash
pytest -q
pytest -q --cov=stream_merge --cov-report=term-missing   # 100% of stream_merge.py
```

Result when this README was written: `36 passed`, coverage `100%`, `ruff check` and `ruff format --check` clean.

## How it works

A `heapq` holds one pending entry per stream: `(time, id, stream_index, amount)`. On each pop the code
drains every copy of the same `(time, id)` key (inside one stream and across streams), compares
amounts, and raises `ConflictingAmountError` **before** the key is yielded. Then it advances only the
streams it consumed. There is no global "seen" set, so nothing grows with the amount of data.

## Complexity

Let `N` be the total number of input events and `k <= 64` the number of streams.

- **Time:** `O(N log k)`. Every event is pushed and popped from a heap of size at most `k`.
- **Space:** `O(k)`. One pending event per stream plus one last-key per stream.

## Memory measurement

Measured with `tracemalloc` (`python measure_memory.py`, Python 3.12.3). Output is consumed without
being stored.

| Input | Events out | Peak memory |
|---|---:|---:|
| 8 streams x 1,000 | 8,000 | 2.0 KiB |
| 8 streams x 10,000 | 80,000 | 1.9 KiB |
| 8 streams x 100,000 | 800,000 | 1.9 KiB |
| 8 streams x 20,000 | 160,000 | 1.9 KiB |
| 32 streams x 20,000 | 640,000 | 7.3 KiB |
| 64 streams x 20,000 | 1,280,000 | 11.4 KiB |
| 1 infinite stream, `islice(500000)` | 500,000 | 0.6 KiB |

Data grows 100x with no change in peak memory; peak grows only with the number of streams.

## Assumptions

- Errors surface on the first `next()`, because `merge` is a generator and reads nothing before that.
- "Sorted" means non-decreasing `(time, id)`. Equal keys with equal amounts are legal; equal keys with
  different amounts are a conflict, not an unsorted-input error.
- An event is valid if it unpacks into exactly three items; no further type validation.
- More than 64 streams raises `TooManyStreamsError`.

## Unfinished

Nothing required by the spec. Not covered: validating the types of `time`, `id` and `amount`.