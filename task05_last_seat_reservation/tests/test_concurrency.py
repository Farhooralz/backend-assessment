"""Real concurrency: independent PostgreSQL connections released by a barrier."""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test import TransactionTestCase

from reservations.models import GymClass, Reservation
from reservations.services import ReservationConflict, reserve

WORKERS = 20
CAPACITY = 3


class CountingBarrier(threading.Barrier):
    """Record how many workers reached the barrier with an already-open connection."""

    def __init__(self, parties: int) -> None:
        """Create a barrier with thread-safe arrival and connection counters."""
        super().__init__(parties)
        self.wait_count = 0
        self.connections_open = 0
        self._count_lock = threading.Lock()

    def wait(self, timeout: float | None = None) -> int:
        """Count the arrival and its open connection, then block until all arrive."""
        with self._count_lock:
            self.wait_count += 1
            self.connections_open += int(connection.connection is not None)
        return super().wait(timeout)


def _open_connection() -> BaseDatabaseWrapper:
    """Open this thread's PostgreSQL connection before it reaches the barrier."""
    connection.close()
    connection.ensure_connection()
    worker_connection = connections[DEFAULT_DB_ALIAS]
    worker_connection.inc_thread_sharing()  # let the main thread close it after the assertions
    return worker_connection


@contextmanager
def _worker_connections() -> Iterator[list[BaseDatabaseWrapper]]:
    """Keep worker connections open through the assertions, then close their sockets."""
    open_connections: list[BaseDatabaseWrapper] = []
    try:
        yield open_connections
    finally:
        for conn in open_connections:
            conn.close()


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

        with _worker_connections() as open_connections:

            def worker(index: int) -> None:
                open_connections.append(_open_connection())
                with pids_lock:
                    backend_pids.add(_backend_pid())
                barrier.wait(timeout=60)
                try:
                    results[index] = reserve(klass.id, user_id=index + 1, key=f"key-{index}")
                except ReservationConflict as exc:
                    assert exc.status_code == 409
                    results[index] = "conflict"

            self._run_workers(worker, WORKERS)

            assert barrier.wait_count == WORKERS
            assert barrier.connections_open == WORKERS
            assert len(backend_pids) == WORKERS
            successes = [result for result in results if isinstance(result, int)]
            conflicts = [result for result in results if result == "conflict"]
            assert len(successes) == 3, results
            assert len(conflicts) == 17, results
            assert Reservation.objects.filter(gym_class=klass).count() == 3

    def test_spec_same_key_same_user_race_returns_one_shared_id(self) -> None:
        """Two simultaneous requests with one key and one user share a single id."""
        klass = GymClass.objects.create(name="Yoga", capacity=1)
        barrier = CountingBarrier(2)
        results: list[int | str | None] = [None, None]

        with _worker_connections() as open_connections:

            def worker(index: int) -> None:
                open_connections.append(_open_connection())
                barrier.wait(timeout=60)
                try:
                    results[index] = reserve(klass.id, user_id=1, key="shared-key")
                except ReservationConflict as exc:
                    results[index] = f"conflict-{exc.status_code}"

            self._run_workers(worker, 2)

            assert barrier.connections_open == 2
            assert results[0] == results[1]
            assert isinstance(results[0], int)
            assert Reservation.objects.count() == 1

    def test_spec_cross_class_key_race_yields_one_success_and_one_409(self) -> None:
        """One user's key racing across two classes hits the real unique-index conflict path."""
        first = GymClass.objects.create(name="Yoga", capacity=1)
        other = GymClass.objects.create(name="Pilates", capacity=1)
        barrier = CountingBarrier(2)
        results: list[int | str | None] = [None, None]
        backend_pids: set[int] = set()
        pids_lock = threading.Lock()

        with _worker_connections() as open_connections:

            def worker(index: int) -> None:
                open_connections.append(_open_connection())
                with pids_lock:
                    backend_pids.add(_backend_pid())
                barrier.wait(timeout=60)
                class_id = first.id if index == 0 else other.id
                try:
                    results[index] = reserve(class_id, user_id=1, key="shared-key")
                except ReservationConflict as exc:
                    results[index] = f"conflict-{exc.status_code}"
                except IntegrityError as exc:
                    results[index] = f"integrity-{type(exc).__name__}"

            self._run_workers(worker, 2)

            assert barrier.wait_count == 2
            assert barrier.connections_open == 2
            assert len(backend_pids) == 2
            successes = [result for result in results if isinstance(result, int)]
            conflicts = [result for result in results if result == "conflict-409"]
            assert len(successes) == 1, results
            assert len(conflicts) == 1, results
            assert Reservation.objects.count() == 1

    def test_spec_independent_connection_per_worker(self) -> None:
        """Each worker holds its own PostgreSQL connection, not a shared cursor."""
        barrier = CountingBarrier(3)
        backend_pids: list[int] = []
        pids_lock = threading.Lock()

        with _worker_connections() as open_connections:

            def worker(_index: int) -> None:
                open_connections.append(_open_connection())
                with pids_lock:
                    backend_pids.append(_backend_pid())
                barrier.wait(timeout=60)

            self._run_workers(worker, 3)

            assert barrier.connections_open == 3
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
