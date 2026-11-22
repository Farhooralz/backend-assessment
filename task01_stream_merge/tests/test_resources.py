"""Task 1 resource tests: memory must be a function of the NUMBER OF STREAMS,
not of the amount of data (docs/TEST_SPEC.md, Task 1)."""

import tracemalloc

from stream_merge import merge


def peak_bytes(n_streams, per_stream):
    def source(idx):
        for t in range(per_stream):
            key_id = idx % 8  # shared ids: the de-duplication path is exercised too
            yield (t, key_id, t * 31 + key_id)

    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        for _ in merge([source(i) for i in range(n_streams)]):
            pass
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak


def test_peak_memory_does_not_grow_when_the_data_grows_25_times():
    small = peak_bytes(64, 200)  # ~12.8k input events
    large = peak_bytes(64, 5000)  # ~320k input events
    assert large < small * 1.5 + 20_000, (small, large)


def test_peak_memory_follows_the_number_of_streams_not_the_amount_of_data():
    few = peak_bytes(2, 20_000)  # 40k events, 2 streams
    many = peak_bytes(64, 20_000 // 32)  # 40k events, 64 streams
    assert few < 50_000, few
    assert many < 200_000, many
