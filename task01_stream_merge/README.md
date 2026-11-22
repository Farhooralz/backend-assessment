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

Result when this README was written: `38 passed`, coverage `100%` (85 statements), `ruff check` and
`ruff format --check` clean with `ruff==0.17.6`.

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

Measured with `tracemalloc` (`python measure_memory.py`, Python 3.12.16). Output is consumed without
being stored.

| Input | Events out | Peak memory |
|---|---:|---:|
| 8 streams x 1,000 | 8,000 | 2.3 KiB |
| 8 streams x 10,000 | 80,000 | 2.1 KiB |
| 8 streams x 100,000 | 800,000 | 2.0 KiB |
| 8 streams x 20,000 | 160,000 | 2.0 KiB |
| 32 streams x 20,000 | 640,000 | 7.3 KiB |
| 64 streams x 20,000 | 1,280,000 | 11.5 KiB |
| 1 infinite stream, `islice(500000)` | 500,000 | 1.2 KiB |

Data grows 100x with no change in peak memory; peak grows only with the number of streams.

## Assumptions

- `merge(...)` validates the stream count eagerly and raises `TooManyStreamsError` at call time when
  more than 64 streams are supplied. No stream is consumed until the first `next()`; every other
  error therefore still surfaces lazily, on the `next()` that reaches it.
- "Sorted" means non-decreasing `(time, id)`. Equal keys with equal amounts are legal; equal keys with
  different amounts are a conflict, not an unsorted-input error.
- An event is valid if it unpacks into exactly three items. Sort-key components (`time`, `id`) must be
  orderable against the first key seen; otherwise `IncompatibleKeyError` names the component, the
  two values and their types. The type of `amount` is not validated.
- `IncompatibleKeyError` is a `MergeError` (and therefore a `ValueError`), like the other errors.
- Dependencies are pinned exactly, including `ruff==0.17.6`, so the quality gate works in a clean clone.

## Mutation spot-check

Three deliberate breakages were applied to `stream_merge.py`, each confirmed to fail tests, then reverted:

| Mutation | Test that caught it |
|---|---|
| Removed the eager `len(iterators) >= MAX_STREAMS` check from `merge()` | `test_spec_too_many_streams_is_rejected_eagerly_at_merge_call_time` (and the older 65-stream test) |
| Added an early `return` to `_check_key_types()` | `test_spec_mixed_type_sort_keys_raise_a_dedicated_error_with_a_helpful_message` (raw `TypeError` from `heapq` returned) |
| Flipped the cross-stream check `other_amount != amount` to `==` | conflict tests in `test_acceptance.py` and `test_properties.py` |

## Unfinished

Nothing required by the spec. Not covered: validating the type of `amount`, or requiring one concrete
type for `time`/`id` (only mutual orderability of keys is checked).