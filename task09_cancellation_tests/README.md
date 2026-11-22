# Task 9 — Reservation cancellation policy: service + independent tests

A minimal Django service decides the refund for cancelling a `confirmed` reservation: the owner or a manager of the same branch may cancel before the start, and the refund comes from the collected payment. The cancellation and its refund document are written in one PostgreSQL transaction; the reservation row is locked with `select_for_update()` before any decision, so two concurrent cancels produce exactly one refund and both callers receive the same result. The test suite never reads the wall clock: it injects `now` and an injectable document writer, then checks both inclusive boundaries and every acceptance sample.

## Layout

| Path | Purpose |
| --- | --- |
| `cancelapp/services.py` | `compute_refund` (pure policy) and `cancel` (permission + locked atomic write) |
| `cancelapp/models.py` | `Branch`, `User`, `Reservation`, `RefundDocument` |
| `cancelapp/errors.py` | Typed rejections (`PermissionDenied`, `ReservationNotCancellable`, `RefundDocumentWriteError`) |
| `cancelapp/settings.py` | PostgreSQL from the shared `POSTGRES_*` env contract (no SQLite) |
| `cancelapp/db_setup.py` | Idempotent `ensure_database()` helper (psycopg, creates `task09` once) |
| `tests/` | 30 spec-driven tests: permission, unit, integration, failure, constraints, concurrency, DB bootstrap |
| `mutation_check.py` | Applies 3 deliberate defects to a temp copy and reports the failing tests |

## Run command

There is no HTTP or CLI app in this task — the runnable entry point is the service itself. From this folder, load the shared env, run the `ensure_db` setup step (idempotent creation of `task09`), then call the policy:

```bash
set -a; . ../.env; set +a
ensure_db() { .venv/bin/python -m cancelapp.db_setup; }
ensure_db
DJANGO_SETTINGS_MODULE=cancelapp.settings .venv/bin/python -c \
  "import django; django.setup(); from datetime import timedelta; from cancelapp.services import compute_refund; print(compute_refund(101, timedelta(hours=24)))"
```

Measured output: `101`. Running `ensure_db` again is a no-op: the helper checks `pg_database` before issuing `CREATE DATABASE`.

## Test commands and measured results

```bash
.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . \
  && (set -a; . ../.env; set +a; .venv/bin/python -m pytest -q) \
  && (set -a; . ../.env; set +a; .venv/bin/python mutation_check.py)
```

- `ruff format .` → `17 files left unchanged`
- `ruff check .` → `All checks passed!`
- `ruff format --check .` → `17 files already formatted`
- `pytest -q` → `30 passed in 0.21–0.22s` across final runs (real PostgreSQL, including the concurrency test; 5 further consecutive concurrency-only runs all passed in 0.13–0.16 s)
- `mutation_check.py` → 3 defects, all **CAUGHT** (table below)

Pure-logic coverage gate:

```bash
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q --cov=cancelapp --cov-report=term-missing
```

Measured output:

```text
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
cancelapp/__init__.py       0      0   100%
cancelapp/db_setup.py      20      0   100%
cancelapp/errors.py         4      0   100%
cancelapp/models.py        16      0   100%
cancelapp/services.py      41      0   100%
cancelapp/settings.py       9      0   100%
-----------------------------------------------------
TOTAL                      90      0   100%
30 passed in 0.29s
```

Environment: Python 3.12.16, PostgreSQL 16, Django 5.2.19, psycopg[binary] 3.2.10, pytest 8.4.2, pytest-django 4.11.1, pytest-cov 7.1.0, pytest-timeout 2.4.0, ruff 0.17.6 — all pinned in `requirements.txt`. The venv is local at `.venv/`. The only coverage exclusion is the `if __name__ == "__main__"` CLI guard in `db_setup.py` (`pragma: no cover`).

## Policy and boundary samples (101 rials)

| Remaining time | Refund | Test(s) |
| --- | --- | --- |
| Exactly 24 h | 101 | `test_spec_exactly_24h_remaining_returns_101`, `test_spec_at_least_24h_returns_full_amount` |
| 24 h minus 1 s (one second later) | 50 | `test_spec_24h_plus_one_second_returns_50`, `test_spec_24h_plus_one_second_later_returns_half` |
| Exactly 2 h | 50 | `test_spec_exactly_2h_remaining_returns_50`, `test_spec_exactly_2h_returns_half` |
| 2 h minus 1 s (one second later) | 0 | `test_spec_2h_plus_one_second_returns_zero`, `test_spec_2h_plus_one_second_later_returns_zero` |
| At the start instant | rejected | `test_spec_at_start_instant_rejected` |

Full refund applies at `>= 24 h`, half at `2 h <= remaining < 24 h`, zero below 2 h; half is floored to whole rials (`101 -> 50`, `1 -> 0`).

## Spec deliverables → evidence

| Deliverable | Where | Test name |
| --- | --- | --- |
| Use pytest and pytest-django | `pytest.ini`, `tests/`; real PostgreSQL vendor asserted | `test_spec_uses_pytest_django` |
| Permission tests (owner, same-branch manager, others) | `tests/test_permission.py` | `test_spec_same_branch_manager_can_cancel`, `test_spec_other_branch_manager_cannot_cancel`, `test_spec_unrelated_user_cannot_cancel` (plus `test_spec_owner_can_cancel`) |
| Unit tests | `tests/test_unit_policy.py` | 7 `test_spec_*` boundary/rounding tests |
| Integration tests | `tests/test_integration.py` | 11 `test_spec_*` tests against PostgreSQL |
| Failure tests | `tests/test_failure.py` | `test_spec_document_write_failure_rolls_back`, `test_spec_failed_write_leaves_no_repeat_result` |
| Control the clock | `now` parameter on `cancel`; no `datetime.now()` in the service | `test_spec_clock_is_injected_not_read_from_wall` (monkeypatches `services.datetime` to raise) |
| Simulate a document-writing failure | injectable `document_writer` | `test_spec_simulates_document_writing_failure`, `test_spec_document_write_failure_rolls_back` |
| Atomic cancellation + refund document | one `transaction.atomic()` block | `test_spec_cancel_records_cancellation_and_refund_document`, `test_spec_document_write_failure_rolls_back` |
| Repeat returns previous result | replay from `RefundDocument` under the row lock | `test_spec_repeat_returns_previous_result`, `test_spec_concurrent_cancels_produce_one_refund_and_same_result` |
| Concurrency safety on real PostgreSQL (reviewer fix) | `select_for_update()` before deciding inside the atomic block; `TransactionTestCase` + `threading.Barrier` + independent connections | `test_spec_concurrent_cancels_produce_one_refund_and_same_result` |
| Idempotent DB bootstrap from env | `ensure_database()` called from `conftest.py`; CLI guard exposed as `ensure_db` in Run command | `test_spec_db_setup_reads_port_and_password_from_env`, `test_spec_db_setup_omits_empty_socket_values`, `test_spec_db_setup_creates_missing_database_once` |
| Three deliberate defects, each mapped to a test name | `mutation_check.py` | `test_spec_three_deliberate_defects_are_defined` (table below) |

## Mutation spot-check

`mutation_check.py` loads `../.env`, copies `cancelapp/`, `tests/`, `pytest.ini` and itself into a temporary directory, applies one defect there, runs the suite against PostgreSQL, and prints the failing test names. The real implementation is never modified. Command:

```bash
set -a; . ../.env; set +a; .venv/bin/python mutation_check.py
```

Measured result table:

| Deliberate defect | Failing tests reported |
| --- | --- |
| `>` instead of `>=` at the 24 h boundary | `test_spec_exactly_24h_remaining_returns_101`, `test_spec_at_least_24h_returns_full_amount` (expected: `test_spec_exactly_24h_remaining_returns_101`) — **CAUGHT** |
| Round half up instead of down (`-(-x // 2)`) | `test_spec_24h_plus_one_second_returns_50`, `test_spec_exactly_2h_remaining_returns_50`, `test_spec_24h_plus_one_second_later_returns_half`, `test_spec_exactly_2h_returns_half`, `test_spec_between_2h_and_24h_returns_half`, `test_spec_half_refund_rounds_down_for_odd_amount` (expected: `test_spec_exactly_2h_remaining_returns_50`) — **CAUGHT** |
| Cancel committed before the refund document | `test_spec_document_write_failure_rolls_back`, `test_spec_failed_write_leaves_no_repeat_result`, `test_spec_concurrent_cancels_produce_one_refund_and_same_result` (expected: `test_spec_document_write_failure_rolls_back`) — **CAUGHT** |

One additional manual mutation was applied to the real `services.py`: removing `.select_for_update()` made the new concurrency test fail with `IntegrityError('duplicate key value violates unique constraint "cancelapp_refunddocument_reservation_id_key"')`; the lock was restored immediately. The same test also failed for the same reason *before* the fix was implemented, which is the test-first evidence for the reviewer finding. No test was weakened.

## Assumptions

- Money is stored as integer rials; "rounded down" means integer floor (`// 2`). No `float` is used.
- "Before it starts" is strict: `now == start` is rejected, as the acceptance sample requires.
- Permission is checked before the repeat shortcut; a replay reads the stored `RefundDocument` and ignores the supplied clock, so it still succeeds after the start.
- The owner need not be a manager. A manager must have `is_manager=True` **and** share the reservation's branch; branch is taken from `reservation.branch`, not from the owner's branch.
- Settings read `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD` with the documented defaults; empty port/password (unix-socket fallback) are passed through as empty strings. PostgreSQL 16 is required by the concurrency test, so SQLite is deliberately not used.
- `ensure_database()` is idempotent and only creates the per-task `task09` database; pytest-django creates `test_task09`. It runs from `conftest.py` before Django's DB setup and can also be invoked as the `ensure_db` step in the Run command.
- The row lock is taken on the reservation inside the existing atomic block, before status/time checks and before the document write. Permission uses the supplied user and the caller's reservation snapshot; those values are immutable during the race.

## Unfinished parts

None. The spec asks for a minimal service plus tests, so there is deliberately no view layer, admin, migration file, or extra feature.
