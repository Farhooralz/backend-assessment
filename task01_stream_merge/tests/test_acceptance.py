"""Task 1 acceptance tests (BDD style: Given / When / Then).

Every test maps to one line of docs/TEST_SPEC.md, Task 1.
Events are (time, id, amount). These tests are the CONTRACT: do not edit them
to make an implementation pass.
"""

import ast
import inspect
import pathlib
import sys
from datetime import UTC, datetime, timedelta

import pytest

import stream_merge
from stream_merge import (
    MAX_STREAMS,
    ConflictingAmountError,
    InvalidEventError,
    MergeError,
    TooManyStreamsError,
    UnsortedStreamError,
    merge,
)


def stream(events):
    """A single-use iterator, like a real terminal stream."""
    yield from events


class OverRead(AssertionError):
    """Raised by a tripwire stream that was read far more than it should be."""


def endless(make_event, tripwire=50_000):
    """A practically infinite stream that fails loudly (instead of eating RAM
    or hanging) if an implementation tries to read it all."""
    i = 0
    while True:
        if i >= tripwire:
            raise OverRead(f"stream was read {tripwire} times: implementation is not lazy")
        yield make_event(i)
        i += 1


# ---------------------------------------------------------------- spec sample
def test_given_the_spec_sample_when_merged_then_order_is_a_b_c_and_a_is_delivered_once():
    # Given two streams that both contain event A
    s1 = stream([(1, "A", 7), (3, "C", 4)])
    s2 = stream([(1, "A", 7), (2, "B", 5)])
    # When they are merged
    out = list(merge([s1, s2]))
    # Then the output is sorted and A appears once
    assert [e[1] for e in out] == ["A", "B", "C"]
    assert out == [(1, "A", 7), (2, "B", 5), (3, "C", 4)]


def test_given_a_changed_amount_for_a_when_merged_then_a_clear_error_is_raised():
    s1 = stream([(1, "A", 7), (3, "C", 4)])
    s2 = stream([(1, "A", 8), (2, "B", 5)])
    with pytest.raises(ConflictingAmountError):
        list(merge([s1, s2]))


def test_given_a_conflict_then_the_error_is_a_value_error_and_names_key_and_amounts():
    with pytest.raises(ConflictingAmountError) as info:
        list(merge([stream([(1, "A", 7)]), stream([(1, "A", 8)])]))
    err = info.value
    assert isinstance(err, ValueError) and isinstance(err, MergeError)
    assert (err.time, err.id) == (1, "A")
    assert {err.first_amount, err.second_amount} == {7, 8}
    message = str(err)
    assert "A" in message and "7" in message and "8" in message


# ------------------------------------------- error comes BEFORE the key is published
def test_given_a_conflict_when_iterating_then_clean_keys_arrive_first_and_the_bad_key_never_does():
    s1 = stream([(0, "Z", 1), (1, "A", 7), (2, "B", 2)])
    s2 = stream([(1, "A", 8)])
    delivered = []
    with pytest.raises(ConflictingAmountError):
        for event in merge([s1, s2]):
            delivered.append(event)
    assert delivered == [(0, "Z", 1)]


def test_given_three_copies_with_one_different_amount_then_the_conflict_is_detected():
    streams = [stream([(1, "A", 7)]), stream([(1, "A", 7)]), stream([(1, "A", 9)])]
    with pytest.raises(ConflictingAmountError):
        list(merge(streams))


def test_given_a_conflict_inside_one_stream_then_it_is_detected():
    with pytest.raises(ConflictingAmountError):
        list(merge([stream([(1, "A", 7), (1, "A", 8)])]))


# ------------------------------------------------ repeats with the same amount: once
def test_given_ten_identical_copies_then_the_event_is_output_once():
    assert list(merge([stream([(5, "X", 10)]) for _ in range(10)])) == [(5, "X", 10)]


def test_given_a_duplicate_inside_one_stream_then_it_is_output_once():
    out = list(merge([stream([(1, "A", 7), (1, "A", 7), (2, "B", 1)])]))
    assert out == [(1, "A", 7), (2, "B", 1)]


def test_given_the_same_id_at_different_times_then_they_are_different_events():
    out = list(merge([stream([(1, "A", 7)]), stream([(2, "A", 8)])]))
    assert out == [(1, "A", 7), (2, "A", 8)]


# --------------------------------------------------- empty input and equal times
def test_given_no_streams_then_the_output_is_empty():
    assert list(merge([])) == []


def test_given_only_empty_streams_then_the_output_is_empty():
    assert list(merge([stream([]), stream([]), stream([])])) == []


def test_given_some_empty_streams_then_they_are_ignored():
    assert list(merge([stream([]), stream([(1, "A", 1)]), stream([])])) == [(1, "A", 1)]


def test_given_equal_times_then_events_are_ordered_by_id():
    s1 = stream([(1, "B", 2), (1, "D", 4)])
    s2 = stream([(1, "A", 1), (1, "C", 3)])
    assert [e[1] for e in merge([s1, s2])] == ["A", "B", "C", "D"]


def test_given_utc_datetimes_as_times_then_they_are_ordered_correctly():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    s1 = stream([(t0, "A", 1), (t0 + timedelta(seconds=2), "C", 3)])
    s2 = stream([(t0 + timedelta(seconds=1), "B", 2)])
    assert [e[1] for e in merge([s1, s2])] == ["A", "B", "C"]


# ------------------------------------------------------------ up to 64 streams
def test_given_exactly_64_streams_then_they_are_accepted():
    assert MAX_STREAMS == 64
    streams = [stream([(i, "S", i)]) for i in range(64)]
    assert len(list(merge(streams))) == 64


def test_given_65_streams_then_a_clear_error_is_raised():
    streams = [stream([]) for _ in range(65)]
    with pytest.raises(TooManyStreamsError):
        list(merge(streams))


def test_spec_too_many_streams_is_rejected_eagerly_at_merge_call_time():
    streams = [stream([(i, "A", 1)]) for i in range(MAX_STREAMS + 1)]
    with pytest.raises(TooManyStreamsError) as info:
        merge(streams)  # no list(), no next(): validation belongs to the call itself
    assert "64" in str(info.value)


def test_given_streams_supplied_by_a_generator_then_they_are_accepted():
    assert list(merge(stream([(1, "A", 1)]) for _ in range(3))) == [(1, "A", 1)]


# ------------------------------------- defensive behaviour (documented assumptions)
def test_given_an_unsorted_stream_then_it_is_reported_instead_of_silently_misordered():
    with pytest.raises(UnsortedStreamError):
        list(merge([stream([(2, "A", 1), (1, "B", 1)])]))


def test_given_a_malformed_event_then_it_is_reported():
    with pytest.raises(InvalidEventError):
        list(merge([stream([(1, "A")])]))


def test_all_module_errors_share_one_base_class():
    for cls in (
        TooManyStreamsError,
        UnsortedStreamError,
        InvalidEventError,
        ConflictingAmountError,
    ):
        assert issubclass(cls, MergeError) and issubclass(MergeError, ValueError)


def test_spec_mixed_type_sort_keys_raise_a_dedicated_error_with_a_helpful_message():
    """Unlike sort-key types must never leak a bare TypeError from heapq or tuple ordering."""
    with pytest.raises(stream_merge.IncompatibleKeyError) as info:
        list(merge([stream([(1, "A", 7)]), stream([("later", "B", 8)])]))
    err = info.value
    assert isinstance(err, MergeError) and isinstance(err, ValueError)
    message = str(err)
    assert "time" in message and "int" in message and "str" in message

    # The same guard covers the id component and keys mixed inside a single stream.
    with pytest.raises(stream_merge.IncompatibleKeyError):
        list(merge([stream([(1, "A", 7)]), stream([(1, 2, 8)])]))
    with pytest.raises(stream_merge.IncompatibleKeyError):
        list(merge([stream([(1, "A", 7), ("later", "B", 8)])]))


# ------------------------------------------------------- lazy / infinite iterators
def test_given_merge_is_called_then_nothing_is_read_until_the_first_item_is_requested():
    reads = []

    def spy():
        for i in range(10):
            reads.append(i)
            yield (i, "A", i)

    merge([spy()])
    assert reads == []


def test_given_an_infinite_stream_when_taking_the_first_1000_then_it_works_and_is_sorted():
    a = endless(lambda i: (i, "a", i))
    b = endless(lambda i: (i, "b", i))
    merged = merge([a, b])
    out = [next(merged) for _ in range(1000)]
    assert out == sorted(out)
    assert len(out) == 1000


def test_given_identical_infinite_streams_then_duplicates_are_collapsed():
    streams = [endless(lambda i: (i, "A", i * 2)) for _ in range(3)]
    merged = merge(streams)
    assert [next(merged) for _ in range(500)] == [(i, "A", i * 2) for i in range(500)]


def test_given_three_streams_then_each_is_read_at_most_n_plus_one_times_for_n_outputs():
    counters = [0, 0, 0]

    def counted(idx):
        i = 0
        while True:
            counters[idx] += 1
            yield (i, f"s{idx}", i)
            i += 1

    merged = merge([counted(0), counted(1), counted(2)])
    n = 30
    for _ in range(n):
        next(merged)
    assert all(c <= n + 1 for c in counters), counters


# ------------------------------------------------------------ standard library only
def test_the_implementation_imports_only_the_standard_library():
    source_file = pathlib.Path(inspect.getsourcefile(stream_merge))
    files = (
        sorted(source_file.parent.rglob("*.py"))
        if source_file.name == "__init__.py"
        else [source_file]
    )
    imported = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
