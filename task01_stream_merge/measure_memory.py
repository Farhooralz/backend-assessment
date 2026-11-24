"""Measure peak memory of merge() to show it depends on stream count, not data size.

Run: python measure_memory.py
"""

import itertools
import tracemalloc

from stream_merge import merge


def stream(name: int, n: int):
    """Yield n sorted events lazily; ids are unique per stream."""
    return ((t, f"s{name}", 1) for t in range(n))


def peak_kib(streams) -> tuple[int, float]:
    """Consume the merge without storing output; return (items, peak KiB)."""
    tracemalloc.start()
    count = sum(1 for _ in merge(streams))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return count, peak / 1024


def main() -> None:
    for n in (1_000, 10_000, 100_000):
        count, peak = peak_kib([stream(k, n) for k in range(8)])
        print(f"8 streams x {n:>7} events -> {count:>8} out, peak {peak:6.1f} KiB")
    for k in (8, 32, 64):
        count, peak = peak_kib([stream(i, 20_000) for i in range(k)])
        print(f"{k:>2} streams x   20000 events -> {count:>8} out, peak {peak:6.1f} KiB")

    infinite = ((t, "A", 1) for t in itertools.count())
    tracemalloc.start()
    for _ in itertools.islice(merge([infinite]), 500_000):
        pass
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"infinite stream, islice 500000 -> peak {peak / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
