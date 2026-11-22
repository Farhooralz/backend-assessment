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

## Run

```bash
cd task05_last_seat_reservation
../.infra-venv/bin/python -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ../.env; set +a
.venv/bin/python manage.py migrate
```

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
- `conftest.py` creates the `task05` database with `psycopg` (tolerating an existing one);
  pytest-django then creates `test_task05`. Empty `POSTGRES_PORT`/`POSTGRES_PASSWORD` are
  passed through as-is for the unix-socket fallback. No Redis is used.

## Unfinished parts

- None for the stated scope.

## Deliverables and measured evidence

Deps pinned: Django 5.2.19, psycopg[binary] 3.2.10, pytest 8.4.2, pytest-django 4.11.1,
pytest-timeout 2.4.0, pytest-cov 6.3.0, ruff 0.17.6. Python 3.14.4, PostgreSQL 16.2.

- **Constraint + migration:** `reservations/migrations/0001_initial.py` creates
  `uniq_reservation_user_class` and `uniq_reservation_user_key`. Tests verify both the model
  metadata and the actual `pg_constraint` rows, plus direct duplicate inserts raising
  `IntegrityError` (`test_spec_unique_user_class_constraint`,
  `test_spec_unique_user_key_constraint`, `test_spec_migration_creates_unique_constraints_in_database`).
- **Barrier test:** 20 threads each close their Django connection, wait on a
  `threading.Barrier(20)` (counted arrivals), then call `reserve` simultaneously. Real output:
  `3` successes, `17` conflicts, `20` distinct connection ids, `4 passed in 0.46s`.
- **Rollback test:** an injected `RuntimeError` after the insert leaves the reservation count
  at `0` and the next ordinary reserve succeeds
  (`test_spec_failure_mid_operation_does_not_consume_capacity`).
- **Lock order:** explained above and pinned by
  `test_spec_select_for_update_locks_class_row_first` (first SELECT contains `FOR UPDATE` on
  `reservations_gymclass`) and `test_spec_no_in_process_lock`.
- **Red step (tests before implementation):**
  `9 failed, 9 passed, 22 warnings in 0.42s` — every failure was `NotImplementedError` from the
  unimplemented `reserve`.
- **Green step:** `.venv/bin/python -m pytest -q` → `18 passed in 0.46s`.
- **Five consecutive concurrency runs** (`pytest -q tests/test_concurrency.py`, real output):

  | Run | Output |
  |---|---|
  | 1 | `.... [100%]` / `4 passed in 0.46s` |
  | 2 | `.... [100%]` / `4 passed in 0.43s` |
  | 3 | `.... [100%]` / `4 passed in 0.43s` |
  | 4 | `.... [100%]` / `4 passed in 0.45s` |
  | 5 | `.... [100%]` / `4 passed in 0.40s` |

## Mutations checked

Each break was applied to `reservations/services.py`, the named tests were run, and the code
was reverted afterwards:

1. Drop `select_for_update()` → `test_spec_20_threads_capacity_3_yields_3_successes_17_conflicts`
   failed with `assert 20 == 3` (all 20 seats succeeded) and
   `test_spec_select_for_update_locks_class_row_first` failed → `2 failed in 0.20s`.
2. Drop the capacity check → `test_spec_full_capacity_conflict_409` failed with
   `Failed: DID NOT RAISE ReservationConflict` and the 20-thread test failed with
   `assert 20 == 3` → `2 failed in 0.29s`.
3. Drop the cross-class key check in `_resolve_existing` →
   `test_spec_same_key_other_class_conflict_409` failed with
   `Failed: DID NOT RAISE ReservationConflict` → `1 failed in 0.15s`.
