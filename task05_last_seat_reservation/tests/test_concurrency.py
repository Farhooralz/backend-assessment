"""Real concurrency: independent PostgreSQL connections released by a barrier."""

import threading
from collections.abc import Callable

from django.db import connection
from django.test import TransactionTestCase

from reservations.models import GymClass, Reservation
from reservations.services import ReservationConflict, reserve

WORKERS = 20
CAPACITY = 3


class CountingBarrier(threading.Barrier):
    """Record how many workers actually reached the shared start point."""

    def __init__(self, parties: int) -> None:
        """Create a barrier with a thread-safe counter."""
        super().__init__(parties)
        self.wait_count = 0
        self._count_lock = threading.Lock()

    def wait(self, timeout: float | None = None) -> int:
        """Count the arrival, then block until every worker has arrived."""
        with self._count_lock:
            self.wait_count += 1
        return super().wait(timeout)


def _backend_pid() -> int:
    """Read the real PostgreSQL backend PID for the current thread's connection."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


class TestReservationConcurrency(TransactionTestCase):
    """TransactionTestCase is required: workers must commit in separate connections."""

    reset_sequences = True

    def _run_workers(self, worker: Callable[[int], None], count: int) -> list[threading.Thread]:
        threads = [threading.Thread(target=worker, args=(index,)) for index in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert all(not thread.is_alive() for thread in threads), "a worker did not finish"
        return threads

    def test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts(self) -> None:
        """Twenty simultaneous users produce exactly three seats and seventeen 409s."""
        klass = GymClass.objects.create(name="Yoga", capacity=CAPACITY)
        barrier = CountingBarrier(WORKERS)
        results: list[int | str | None] = [None] * WORKERS
        backend_pids: set[int] = set()
        pids_lock = threading.Lock()

        def worker(index: int) -> None:
            connection.close()
            barrier.wait(timeout=60)
            connection.ensure_connection()
            with pids_lock:
                backend_pids.add(_backend_pid())
            try:
                results[index] = reserve(klass.id, user_id=index + 1, key=f"key-{index}")
            except ReservationConflict as exc:
                assert exc.status_code == 409
                results[index] = "conflict"
            finally:
                connection.close()

        self._run_workers(worker, WORKERS)

        assert barrier.wait_count == WORKERS
        assert len(backend_pids) == WORKERS
        successes = [result for result in results if isinstance(result, int)]
        conflicts = [result for result in results if result == "conflict"]
        assert len(successes) == 3, results
        assert len(conflicts) == 17, results
        assert Reservation.objects.filter(gym_class=klass).count() == 3

    def test_spec_same_key_same_user_race_returns_one_shared_id(self) -> None:
        """Two simultaneous requests with one key and one user share a single id."""
        klass = GymClass.objects.create(name="Yoga", capacity=1)
        barrier = threading.Barrier(2)
        results: list[int | str | None] = [None, None]

        def worker(index: int) -> None:
            connection.close()
            barrier.wait(timeout=60)
            try:
                results[index] = reserve(klass.id, user_id=1, key="shared-key")
            except ReservationConflict as exc:
                results[index] = f"conflict-{exc.status_code}"
            finally:
                connection.close()

        self._run_workers(worker, 2)

        assert results[0] == results[1]
        assert isinstance(results[0], int)
        assert Reservation.objects.count() == 1

    def test_spec_independent_connection_per_worker(self) -> None:
        """Each worker holds its own PostgreSQL connection, not a shared cursor."""
        barrier = threading.Barrier(3)
        backend_pids: list[int] = []

        def worker(_index: int) -> None:
            connection.close()
            barrier.wait(timeout=60)
            connection.ensure_connection()
            backend_pids.append(_backend_pid())
            connection.close()

        self._run_workers(worker, 3)

        assert len(backend_pids) == 3
        assert len(set(backend_pids)) == 3

    def test_spec_shared_start_barrier(self) -> None:
        """No worker proceeds until all of them reached the same start point."""
        released = threading.Event()
        barrier = threading.Barrier(4, action=released.set)
        observed: list[bool] = []

        def worker(_index: int) -> None:
            barrier.wait(timeout=60)
            observed.append(released.is_set())

        self._run_workers(worker, 4)

        assert observed == [True, True, True, True]
