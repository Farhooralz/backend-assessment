# Task 5 — Last-seat reservation

`reserve(class_id, user_id, key)` gives one user at most one seat in a fixed-capacity class,
reuses the same reservation id for a repeated successful key, and reports conflicts with a
`ReservationConflict` exception carrying HTTP status 409. The correctness lives in a plain
service (`reservations/services.py`) backed by PostgreSQL row locks and two unique constraints;
no in-process lock is used.

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
   re-read that returns the winning reservation's id. `COMMIT` releases all locks.

The order is always **class row first, then user-scoped rows, never the reverse**: reversing it
would let worker A hold the class row while waiting for a user-scoped entry and worker B hold
that entry while waiting for the class row — a deadlock. A `threading.Lock` is not acceptable
because independent workers are separate processes with separate memory; only the database
row lock is shared by all connections.

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

## Assumptions

- 409 is represented by `ReservationConflict.status_code == 409`. The exercise asks for the
  `reserve` operation, not an HTTP adapter, so no view/URL layer is included.
- `user_id` is an integer supplied by the caller; no auth/user app is required.
- The caller supplies one stable idempotency key per logical request.
- Direct PostgreSQL connections are assumed (no external pooler), so each worker's
  `SELECT pg_backend_pid()` is a distinct real backend PID.
- `task05` is created by `ensure_db`/`ensure_database()`; empty `POSTGRES_PORT` /
  `POSTGRES_PASSWORD` are passed through as-is for the unix-socket fallback. No Redis is used.

## Unfinished parts

- None for the stated scope.

## Deliverables and measured evidence

Deps pinned: Django 5.2.19, psycopg[binary] 3.2.10, pytest 8.4.2, pytest-django 4.11.1,
pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6. Python 3.12.16, PostgreSQL 16.2.

- **Constraint + migration:** `reservations/migrations/0001_initial.py` creates
  `uniq_reservation_user_class` and `uniq_reservation_user_key`. Tests verify both the model
  metadata and the actual `pg_constraint` rows, plus direct duplicate inserts raising
  `IntegrityError` (`test_spec_unique_user_class_constraint`,
  `test_spec_unique_user_key_constraint`, `test_spec_migration_creates_unique_constraints_in_database`).
- **Barrier test with real backend PIDs:** 20 threads each close their Django connection, wait
  on a `threading.Barrier(20)` with counted arrivals, then record `SELECT pg_backend_pid()`
  from their own connection (never Python `id()`). `test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts`
  asserts 3 successes, 17 conflicts, `barrier.wait_count == 20` and **20 distinct PostgreSQL
  backend PIDs**. `test_spec_independent_connection_per_worker` uses PIDs as well.
  Real run: `3` successes, `17` conflicts, `4 passed in 0.29s`.
- **Same-key same-user race:** `test_spec_same_key_same_user_race_returns_one_shared_id`
  gives both threads one shared id and one stored reservation.
- **Rollback test:** an injected `RuntimeError` after the insert leaves the reservation count
  at `0` and the next ordinary reserve succeeds
  (`test_spec_failure_mid_operation_does_not_consume_capacity`).
- **Lock order:** explained above and pinned by
  `test_spec_select_for_update_locks_class_row_first` (first SELECT contains `FOR UPDATE` on
  `reservations_gymclass`) and `test_spec_no_in_process_lock`.
- **Reproducibility:** the shared helper and management command are pinned by
  `test_spec_ensure_database_is_idempotent`, `test_spec_ensure_db_management_command` and
  `test_spec_conftest_uses_shared_ensure_database`. Red step (before extracting the helper):
  `1 error in 0.11s` at collection with `ModuleNotFoundError: No module named 'reservations.db'`.
  After implementation, `manage.py ensure_db` printed `Database task05 is ready.` and
  `manage.py migrate` completed with `Applying reservations.0001_initial... OK`.
- **Green step:** `.venv/bin/python -m pytest -q` → `21 passed in 0.38s`.

**Five consecutive concurrency runs** (`pytest -q tests/test_concurrency.py`, real output):

| Run | Output |
|---|---|
| 1 | `.... [100%]` / `4 passed in 0.29s` |
| 2 | `.... [100%]` / `4 passed in 0.29s` |
| 3 | `.... [100%]` / `4 passed in 0.27s` |
| 4 | `.... [100%]` / `4 passed in 0.27s` |
| 5 | `.... [100%]` / `4 passed in 0.26s` |

## Mutations checked

Each break was applied to `reservations/services.py`, the named tests were run, and the code
was reverted afterwards:

1. Drop `select_for_update()` → `test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts`
   failed with `assert 5 == 3` and `test_spec_select_for_update_locks_class_row_first` failed →
   `2 failed in 0.36s`.
2. Drop the capacity check → `test_spec_full_capacity_conflict_409` failed with
   `Failed: DID NOT RAISE ReservationConflict` and the 20-thread test failed with
   `assert 20 == 3` → `2 failed in 0.25s`.
3. Drop the cross-class key check in `_resolve_existing` →
   `test_spec_same_key_other_class_conflict_409` failed with
   `Failed: DID NOT RAISE ReservationConflict` → `1 failed in 0.13s`.
