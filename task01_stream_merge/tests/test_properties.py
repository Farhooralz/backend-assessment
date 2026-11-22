"""Task 1 property-based tests (Hypothesis): the implementation is compared with a
trivially-correct reference model on thousands of generated inputs."""

import itertools
import random

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from stream_merge import MAX_STREAMS, ConflictingAmountError, merge

KEYS = st.tuples(st.integers(0, 25), st.sampled_from("ABCDEF"))
AMOUNTS = st.integers(-1000, 1000)


def stream(events):
    yield from events


@st.composite
def consistent_streams(draw):
    """Several sorted streams drawn from one universe, so equal keys always carry
    equal amounts. Some events are repeated inside a stream."""
    universe = draw(st.dictionaries(KEYS, AMOUNTS, max_size=30))
    keys = sorted(universe)
    streams = []
    for _ in range(draw(st.integers(0, 8))):
        chosen = [k for k in keys if draw(st.booleans())]
        events = []
        for k in chosen:
            events += [(k[0], k[1], universe[k])] * draw(st.integers(1, 2))
        streams.append(events)
    return universe, streams


def reference(streams):
    merged = {}
    for events in streams:
        for t, i, a in events:
            merged[(t, i)] = a
    return [(t, i, a) for (t, i), a in sorted(merged.items())]


@settings(max_examples=300, deadline=None)
@given(consistent_streams())
def test_merge_equals_the_reference_model(data):
    _, streams = data
    assert list(merge([stream(s) for s in streams])) == reference(streams)


@settings(max_examples=200, deadline=None)
@given(consistent_streams())
def test_output_keys_are_strictly_increasing(data):
    _, streams = data
    out = list(merge([stream(s) for s in streams]))
    keys = [(t, i) for t, i, _ in out]
    assert all(a < b for a, b in itertools.pairwise(keys))


@settings(max_examples=200, deadline=None)
@given(consistent_streams(), st.randoms(use_true_random=False))
def test_the_order_of_the_streams_does_not_matter(data, rnd):
    _, streams = data
    shuffled = list(streams)
    rnd.shuffle(shuffled)
    assert list(merge([stream(s) for s in streams])) == list(merge([stream(s) for s in shuffled]))


@settings(max_examples=200, deadline=None)
@given(consistent_streams(), st.data())
def test_a_planted_conflict_raises_and_only_smaller_keys_are_delivered_first(data, draw):
    _, streams = data
    all_events = sorted({(t, i, a) for s in streams for (t, i, a) in s})
    assume(all_events)  # nothing to corrupt in an empty universe
    victim = draw.draw(st.sampled_from(all_events))
    bad = (victim[0], victim[1], victim[2] + 1)

    delivered = []
    with pytest.raises(ConflictingAmountError):
        for event in merge([stream(s) for s in streams] + [stream([bad])]):
            delivered.append(event)

    assert (victim[0], victim[1]) not in {(t, i) for t, i, _ in delivered}
    assert delivered == [e for e in reference(streams) if (e[0], e[1]) < (victim[0], victim[1])]


@pytest.mark.parametrize("seed", range(5))
def test_64_streams_of_overlapping_data_match_the_reference(seed):
    rng = random.Random(seed)
    universe = {(rng.randint(0, 60), rng.choice("ABCDEFGH")): rng.randint(1, 9) for _ in range(200)}
    streams = []
    for _ in range(MAX_STREAMS):
        chosen = sorted(k for k in universe if rng.random() < 0.3)
        streams.append([(t, i, universe[(t, i)]) for t, i in chosen])
    assert list(merge([stream(s) for s in streams])) == reference(streams)
