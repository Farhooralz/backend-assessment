# Task 5 — Last-seat reservation

`reserve(class_id, user_id, key)` gives one user at most one seat in a fixed-capacity class,
reuses the same reservation id for a repeated successful key, reports conflicts with a
`ReservationConflict` exception carrying HTTP status 409, and reports an unknown class with a
`ClassNotFound` exception carrying HTTP status 404. The correctness lives in a plain service
(`reservations/services.py`) backed by PostgreSQL row locks and two unique constraints; no
in-process lock is used.

## Lock order

1. `BEGIN` opens one transaction for the whole operation.
2. `SELECT ... FROM reservations_gymclass WHERE id = ... FOR UPDATE` locks the **class row first**.
   Every worker reserving the same class queues on this single row lock, so the capacity check
   and the insert are serialised for that class while different classes stay independent.
3. Only after that lock is held does the service read the user-scoped rows (idempotency key,
   then the user's existing reservation for that class) and insert a new reservation. The
   unique indexes `uniq_reservation_user_key` and `uniq_reservation_user_class` take their
   index-entry locks **after** the class lock, never before.
4. A nested `atomic()` savepoint turns an `IntegrityError` from the idempotency race into a
   re-read that returns the winning reservation's id; when the same key won a *different* class,
   `_resolve_existing` raises the 409 conflict instead. `COMMIT` releases all locks.

The order is always **class row first, then user-scoped rows, never the reverse**: reversing it
would let worker A hold the class row while waiting for a user-scoped entry and worker B hold
that entry while waiting for the class row — a deadlock. A `threading.Lock` is not acceptable
because independent workers are separate processes with separate memory; only the database
row lock is shared by all connections.

This is not just prose: `test_spec_select_for_update_locks_class_row_first` captures the first
`SELECT` of `reserve()` and asserts it locks `reservations_gymclass` with `FOR UPDATE`;
`test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts` proves the capacity check is
serialised (exactly 3 of 20 workers win); `test_spec_cross_class_key_race_yields_one_success_and_one_409`
proves a different class contending on the same user-scoped key waits for the winner's commit and
then returns 409; `test_spec_failure_after_insert_rolls_back_separate_connection` proves the row
and the seat are both released when the transaction fails. The two `test_extra_*` source/README
checks below are deliverable-presence checks only.

## Infrastructure and Run

From the repository root, start real PostgreSQL 16 with one of the two documented options:

```bash
# Option A — Docker
cp -n .env.example .env && docker compose up -d

# Option B — no-Docker fallback (creates .env and starts PostgreSQL + Redis)
scripts/local_infra.sh start
scripts/local_infra.sh status
```

Then, from this task folder (Python 3.12+):

```bash
cd task05_last_seat_reservation
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ../.env; set +a
.venv/bin/python manage.py ensure_db   # creates task05 if absent, idempotent
.venv/bin/python manage.py migrate
```

`manage.py ensure_db` calls `reservations.db.ensure_database()`, the same helper used by the
pytest fixture, so a fresh checkout is migratable before any test has run.

## Test

```bash
cd task05_last_seat_reservation
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q
```

Full quality gate (same folder, env loaded):

```bash
set -a; . ../.env; set +a
.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q
```

## Assumptions

- 409 is represented by `ReservationConflict.status_code == 409`. The exercise asks for the
  `reserve` operation, not an HTTP adapter, so no view/URL layer is included.
- ⚠ An unknown `class_id` raises `ClassNotFound(status_code == 404)`. The spec only defines 409
  conflict cases; the Round-2 brief explicitly asks for a defined 404-mapped error, so this is an
  added error type rather than a spec conflict case.
- `user_id` is an integer supplied by the caller; no auth/user app is required.
- The caller supplies one stable idempotency key per logical request.
- Direct PostgreSQL connections are assumed (no external pooler), so each worker's
  `SELECT pg_backend_pid()` is a distinct real backend PID.
- `task05` is created by `ensure_db`/`ensure_database()`; empty `POSTGRES_PORT` /
  `POSTGRES_PASSWORD` are passed through as-is for the unix-socket fallback. No Redis is used.

## Unfinished parts

- None for the stated scope.

## Deliverables and measured evidence

Pinned deps: Django 5.2.19, psycopg[binary] 3.2.10, pytest 8.4.2, pytest-django 4.11.1,
pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6. Measured Python 3.12.16, PostgreSQL 16.2
(`SHOW server_version`).

- **Constraint + migration:** `reservations/migrations/0001_initial.py` creates
  `uniq_reservation_user_class` and `uniq_reservation_user_key`. Tests verify both the model
  metadata and the real `pg_constraint` rows, plus direct duplicate inserts raising
  `IntegrityError` (`test_spec_unique_user_class_constraint`,
  `test_spec_unique_user_key_constraint`, `test_spec_migration_creates_unique_constraints_in_database`).
  `test_extra_migration_file_present` is an extra file-presence check.
- **Barrier with real backends:** 20 threads each open a connection *before* waiting on a
  `CountingBarrier(20)`, record `SELECT pg_backend_pid()` from their own connection, and keep
  the socket open until after the assertions; the main thread then closes them via
  `inc_thread_sharing()`. `test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts`
  asserts 3 successes, 17 conflicts, `wait_count == 20`, `connections_open == 20` and 20 distinct
  backend PIDs. `test_spec_independent_connection_per_worker` also asserts three distinct PIDs.
  Five consecutive runs of `pytest -q tests/test_concurrency.py` each printed `5 passed` with no
  teardown warnings.
- **Same-key same-user race:** `test_spec_same_key_same_user_race_returns_one_shared_id` gives
  both threads one shared id and one stored row.
- **Cross-class key race:** `test_spec_cross_class_key_race_yields_one_success_and_one_409` runs
  two classes, one user and one key over two real connections; exactly one reserve succeeds, the
  loser returns a 409 conflict from the unique-index `IntegrityError` re-read path, and one row is
  stored.
- **Rollback:** `test_spec_failure_after_insert_rolls_back_separate_connection` uses
  `transaction=True`, fails through the post-`_insert` seam while the class row is still locked,
  reads `0` rows from a **separate psycopg connection** on a capacity-1 class, then shows a normal
  reserve succeeds. `test_spec_failure_mid_operation_does_not_consume_capacity` keeps the original
  in-transaction check.
- **Error mapping:** `test_spec_unknown_class_id_raises_class_not_found_404`.
- **Reproducibility:** the shared helper and management command are pinned by
  `test_spec_ensure_database_is_idempotent` and `test_spec_ensure_db_management_command`;
  `test_extra_conftest_uses_shared_ensure_database` is an extra source check.
- **Grep-as-proof demotion:** `test_extra_no_in_process_lock_source_check` and
  `test_extra_lock_order_documented_in_readme` are explicit `test_extra_*` presence checks; each
  deliverable also has a behavioural test listed above.
- **Counts:** `.venv/bin/python -m pytest --collect-only -q | tail -1` prints
  `24 tests collected in 0.02s`. Full gate: `ruff format .` → `19 files left unchanged`,
  `ruff check .` → `All checks passed!`, `ruff format --check .` → `19 files already formatted`,
  `pytest -q` → `24 passed`.

## Round 2

Red-first evidence from the **unmodified** Round-1 code (each command actually run, then the fix
applied). Failing lines are copied verbatim.

1. **Rollback test — code bug not reproduced; testability gap fixed.** The old test injected the
   failure inside `create()` and used the default Django transaction wrapper, so it never proved
   a post-`_insert` failure. Adding the stronger test to the unmodified service gave
   `tests/test_behavior.py:108: Failed: DID NOT RAISE <class 'RuntimeError'>` because no seam
   existed (together with finding 4). A no-op `_after_insert()` seam inside
   the outer `atomic()` makes it pass; the separate-connection read then proves `0` rows and a
   free seat, and a subsequent reserve succeeds. The atomic boundary is real: moving the hook
   outside `atomic()` fails with `assert 1 == 0` (mutation 4 below).
2. **Cross-class key race — bug not reproduced.** The new
   `test_spec_cross_class_key_race_yields_one_success_and_one_409` passed against the unmodified
   service (the only warning came from the test holding proxy objects instead of per-thread
   wrappers, fixed before the final gate). Final runs: five consecutive
   `pytest -q tests/test_concurrency.py` runs each printed `5 passed`, no warnings. The existing
   monkeypatch test was renamed `test_unit_integrity_error_rereads_shared_id` and is kept only as
   a unit test of the re-read branch.
3. **Barrier ordering — test defect reproduced.**
   `tests/test_concurrency.py:83: AssertionError: assert 0 == 20` for
   `barrier.connections_open == WORKERS` on the unmodified tests. Fixed by opening the connection
   before `barrier.wait()` in every DB worker and closing only after the PID assertions.
4. **Unknown class — bug reproduced.**
   `tests/test_behavior.py:39: AssertionError: assert 'DoesNotExist' == 'ClassNotFound'`. Fixed by
   the `ClassNotFound` exception (`status_code = 404`) raised from `reserve()`.
5. **Grep-as-proof — structural weakness reproduced (no runtime bug).** The four source/README
   greps were renamed to `test_extra_*`; their deliverables are now backed by the behavioural
   tests named in the lock-order paragraph and in the mutation table below.

### Mutations checked (Round 2)

Each mutation touched business logic in `reservations/services.py`, the named test was run, and
the original file was restored from a backup before the final gate.

| # | Mutation | Exact failing test (`file::test_name`) | Observed failure |
|---|---|---|---|
| 1 | Drop `select_for_update()` → plain `.get()` | `tests/test_concurrency.py::TestReservationConcurrency::test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts` and `tests/test_deliverables.py::test_spec_select_for_update_locks_class_row_first` | `assert 17 == 3` (2 tests failed) |
| 2 | Capacity `>=` → `>` | `tests/test_behavior.py::test_spec_full_capacity_conflict_409` | `Failed: DID NOT RAISE <class 'reservations.services.ReservationConflict'>` |
| 3 | Remove the outer `transaction.atomic()` | `tests/test_behavior.py::test_spec_failure_after_insert_rolls_back_separate_connection` | `TransactionManagementError: select_for_update cannot be used outside of a transaction.` |
| 4 | Move the post-insert hook outside `atomic()` (failure after COMMIT) | `tests/test_behavior.py::test_spec_failure_after_insert_rolls_back_separate_connection` | separate connection read `assert 1 == 0` |
| 5 | Remove the `ClassNotFound` mapping (let `DoesNotExist` escape) | `tests/test_behavior.py::test_spec_unknown_class_id_raises_class_not_found_404` | `assert 'DoesNotExist' == 'ClassNotFound'` |

Final state after all reverts: `24 passed`.
