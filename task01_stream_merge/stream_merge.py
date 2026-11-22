"""Lazy k-way merge of sorted payment-event iterators.

Only one pending event per input stream is retained, so memory scales with the
number of streams rather than with the number of events.
"""

import heapq
from collections.abc import Iterable, Iterator
from typing import Any

MAX_STREAMS = 64

_Key = tuple[Any, Any]
_Entry = tuple[Any, Any, int, Any]
Event = tuple[Any, Any, Any]


class MergeError(ValueError):
    """Base class for every error raised by this module."""


class TooManyStreamsError(MergeError):
    """Raised when more than MAX_STREAMS iterators are supplied."""


class UnsortedStreamError(MergeError):
    """Raised when an input stream is not sorted by (time, id)."""


class InvalidEventError(MergeError):
    """Raised when a yielded item is not a three-field event."""


class ConflictingAmountError(MergeError):
    """Raised when one key carries two different amounts."""

    def __init__(self, time: Any, id: Any, first_amount: Any, second_amount: Any) -> None:
        self.time = time
        self.id = id
        self.first_amount = first_amount
        self.second_amount = second_amount
        super().__init__(
            f"conflicting amount for key ({time!r}, {id!r}): {first_amount} != {second_amount}"
        )


def _read_event(stream: Iterator[Any], index: int, last_keys: list[_Key | None]) -> _Entry | None:
    """Read one event, validate its shape and order, and return a heap entry."""
    try:
        item = next(stream)
    except StopIteration:
        return None
    try:
        time, ident, amount = item
    except (TypeError, ValueError) as exc:
        raise InvalidEventError(
            f"stream {index}: expected (time, id, amount), got {item!r}"
        ) from exc

    key: _Key = (time, ident)
    previous = last_keys[index]
    if previous is not None and key < previous:
        raise UnsortedStreamError(
            f"stream {index}: key {key!r} is before previous key {previous!r}"
        )
    last_keys[index] = key
    return (time, ident, index, amount)


def _consume_key(
    stream: Iterator[Any],
    index: int,
    key: _Key,
    amount: Any,
    last_keys: list[_Key | None],
) -> _Entry | None:
    """Skip repeated copies of key in one stream, checking their amounts."""
    while True:
        entry = _read_event(stream, index, last_keys)
        if entry is None or (entry[0], entry[1]) != key:
            return entry
        if entry[3] != amount:
            raise ConflictingAmountError(key[0], key[1], amount, entry[3])


def merge(streams: Iterable[Iterator[Any]]) -> Iterator[Event]:
    """Merge sorted event iterators into one lazy, de-duplicated sorted iterator."""
    iterators: list[Iterator[Any]] = []
    for stream in streams:
        if len(iterators) >= MAX_STREAMS:
            raise TooManyStreamsError(f"at most {MAX_STREAMS} streams are supported")
        iterators.append(iter(stream))

    last_keys: list[_Key | None] = [None] * len(iterators)
    heap: list[_Entry] = []
    for index, stream in enumerate(iterators):
        entry = _read_event(stream, index, last_keys)
        if entry is not None:
            heapq.heappush(heap, entry)

    while heap:
        time, ident, index, amount = heapq.heappop(heap)
        key: _Key = (time, ident)

        entry = _consume_key(iterators[index], index, key, amount, last_keys)
        if entry is not None:
            heapq.heappush(heap, entry)

        while heap and (heap[0][0], heap[0][1]) == key:
            _, _, other_index, other_amount = heapq.heappop(heap)
            if other_amount != amount:
                raise ConflictingAmountError(time, ident, amount, other_amount)
            entry = _consume_key(iterators[other_index], other_index, key, amount, last_keys)
            if entry is not None:
                heapq.heappush(heap, entry)

        yield (time, ident, amount)
