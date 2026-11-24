# Task 9 — Reservation cancellation policy: service + independent tests

A minimal Django service decides the refund for cancelling a `confirmed` reservation: the owner or a manager of the same branch may cancel before the start, and the refund comes from the collected payment. The cancellation and its refund document are written in one PostgreSQL transaction; the reservation row is locked with `select_for_update()` before any decision, so two concurrent cancels produce exactly one refund and both callers receive the same result. Callers pass `now`, or omit it to use the service's one default clock, `django.utils.timezone.now()`; tests either inject a fixed `now` or patch that exact clock. An injectable document writer lets the failure tests insert the document and then fail.

## Layout

| Path | Purpose |
| --- | --- |
| `cancelapp/services.py` | `compute_refund` (pure policy) and `cancel` (permission + locked atomic write, injectable `now` and writer) |
| `cancelapp/models.py` | `Branch`, `User`, `Reservation`, `RefundDocument` |
| `cancelapp/errors.py` | Typed rejections (`PermissionDenied`, `ReservationNotCancellable`, `RefundDocumentWriteError`, `InconsistentStateError`) |
| `cancelapp/settings.py` | PostgreSQL from the shared `POSTGRES_*` env contract (no SQLite) |
| `cancelapp/db_setup.py` | Idempotent `ensure_database()` helper (psycopg, creates `task09` once) |
| `tests/` | 30 spec-driven tests: permission, unit, integration, failure, constraints, concurrency, DB bootstrap |
| `mutation_check.py` | Applies 3 deliberate defects to a temp copy and reports the failing test ids |

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
- `pytest -q` → `30 passed` (real PostgreSQL 16.2, including the concurrency test)
- `mutation_check.py` → 3 defects, all **CAUGHT** (table below)

Test count is confirmed by `pytest --collect-only -q | tail -1` → `30 tests collected`. No timing numbers are claimed: they vary between runs.

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
cancelapp/errors.py         5      0   100%
cancelapp/models.py        16      0   100%
cancelapp/services.py      47      0   100%
cancelapp/settings.py       9      0   100%
-----------------------------------------------------
TOTAL                      97      0   100%
30 passed
```

Environment: Python 3.12.16, PostgreSQL 16.2 (measured with `SHOW server_version`), Django 5.2.19, psycopg[binary] 3.2.10, pytest 8.4.2, pytest-django 4.11.1, pytest-cov 7.1.0, pytest-timeout 2.4.0, coverage 7.17.4, ruff 0.17.6 — all pinned in `requirements.txt`. The venv is local at `.venv/`. The only coverage exclusion is the `if __name__ == "__main__"` CLI guard in `db_setup.py` (`pragma: no cover`).

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

| Deliverable | Where | Test name(s) |
| --- | --- | --- |
| Use pytest and pytest-django | `pytest.ini`, `tests/`; real PostgreSQL vendor asserted | `test_spec_uses_pytest_django` |
| Permission tests (owner, same-branch manager, others) | `tests/test_permission.py` (3) | `test_spec_same_branch_manager_can_cancel`, `test_spec_other_branch_manager_cannot_cancel`, `test_spec_unrelated_user_cannot_cancel` (plus `test_spec_owner_can_cancel`) |
| Unit tests | `tests/test_unit_policy.py` (7) | 7 `test_spec_*` boundary/rounding tests |
| Integration tests | `tests/test_integration.py` (13) | 13 `test_spec_*` tests against PostgreSQL |
| Failure tests | `tests/test_failure.py` (2) | `test_spec_document_write_failure_rolls_back`, `test_spec_failed_write_leaves_no_repeat_result` |
| Control the clock | `now` defaults to `timezone.now()`; one clock patched in tests | `test_spec_default_clock_is_timezone_now`, `test_spec_explicit_now_does_not_read_default_clock` |
| Simulate a document-writing failure | `_creating_then_failing_writer`: INSERT then raise | `test_spec_document_write_failure_rolls_back`, `test_spec_failed_write_leaves_no_repeat_result` |
| Atomic cancellation + refund document | one `transaction.atomic()` block | `test_spec_cancel_records_cancellation_and_refund_document`, `test_spec_document_write_failure_rolls_back` |
| Explicit inconsistent-state error | `InconsistentStateError` on replay without a document | `test_spec_cancelled_without_document_raises_inconsistent_state` |
| Repeat returns previous result | replay from `RefundDocument` under the row lock | `test_spec_repeat_returns_previous_result`, `test_spec_concurrent_cancels_produce_one_refund_and_same_result` |
| Concurrency safety on real PostgreSQL | `select_for_update()` before deciding inside the atomic block; `TransactionTestCase` + `threading.Barrier` + independent connections | `test_spec_concurrent_cancels_produce_one_refund_and_same_result` |
| Idempotent DB bootstrap from env | `ensure_database()` from `conftest.py`; `ensure_db` in Run command | `test_spec_db_setup_reads_port_and_password_from_env`, `test_spec_db_setup_omits_empty_socket_values`, `test_spec_db_setup_creates_missing_database_once` |
| Three deliberate defects, each mapped to a test id | `mutation_check.py` | table below |

## Mutation spot-check

`mutation_check.py` loads `../.env`, copies `cancelapp/`, `tests/`, `pytest.ini` and itself into a temporary directory, applies one defect there, runs the suite against PostgreSQL, and prints the failing test ids. The real implementation is never modified. Command:

```bash
set -a; . ../.env; set +a; .venv/bin/python mutation_check.py
```

Measured result table (full test ids, exactly as printed):

| Deliberate defect | Named test that must catch it | All failing test ids reported | Result |
| --- | --- | --- | --- |
| `>` instead of `>=` at the 24 h boundary | `tests/test_integration.py::test_spec_exactly_24h_remaining_returns_101` | `tests/test_integration.py::test_spec_exactly_24h_remaining_returns_101`, `tests/test_unit_policy.py::test_spec_at_least_24h_returns_full_amount` | CAUGHT |
| Round half up instead of down (`-(-x // 2)`) | `tests/test_integration.py::test_spec_exactly_2h_remaining_returns_50` | `tests/test_integration.py::test_spec_24h_plus_one_second_returns_50`, `tests/test_integration.py::test_spec_exactly_2h_remaining_returns_50`, `tests/test_integration.py::test_spec_default_clock_is_timezone_now`, `tests/test_unit_policy.py::test_spec_24h_plus_one_second_later_returns_half`, `tests/test_unit_policy.py::test_spec_exactly_2h_returns_half`, `tests/test_unit_policy.py::test_spec_between_2h_and_24h_returns_half`, `tests/test_unit_policy.py::test_spec_half_refund_rounds_down_for_odd_amount` | CAUGHT |
| Remove `transaction.atomic()` | `tests/test_failure.py::test_spec_document_write_failure_rolls_back` | `tests/test_concurrency.py::TestConcurrentCancel::test_spec_concurrent_cancels_produce_one_refund_and_same_result`, `tests/test_failure.py::test_spec_document_write_failure_rolls_back`, `tests/test_failure.py::test_spec_failed_write_leaves_no_repeat_result` | CAUGHT |

Defect 3 also drops `select_for_update()`: Django raises `TransactionManagementError` for a `select_for_update()` in autocommit mode, so a no-transaction build cannot keep that lock. The business change is still the missing transaction, and the named test fails for that reason: `assert _committed_state(reservation.pk) == ("confirmed", 0)` → `AssertionError: assert ('confirmed', 1) == ('confirmed', 0)`. The write is verified through a separate psycopg connection, after the INSERT has happened.

## Round 2

All five findings reproduced; there are no "not reproduced" items.

1. **Atomicity test passed for the wrong reason — reproduced.** Before the fix, the writer only raised; no write preceded the failure. A temporary no-transaction build ran `pytest tests/test_failure.py::test_spec_document_write_failure_rolls_back` and printed `1 passed`, proving the defect survived. The rewritten test makes the writer insert a `RefundDocument` and then raise, uses `transaction=True`, and checks a separate connection. Under the no-transaction defect its failing line is:

   ```text
   tests/test_failure.py:51: in test_spec_document_write_failure_rolls_back
       assert _committed_state(reservation.pk) == ("confirmed", 0)
   E   AssertionError: assert ('confirmed', 1) == ('confirmed', 0)
   ```

   The `len(created_ids) == 1` assertion in the same test proves the failure was injected after the INSERT.

2. **Defect 3 replaced — reproduced.** The old third defect (`cancel committed before refund document`) changed write ordering but kept the transaction, so it was not an atomicity check. It is now `remove transaction.atomic() (and the row lock it requires)` in `mutation_check.py`; the fresh table above names `tests/test_failure.py::test_spec_document_write_failure_rolls_back` and all real failing test ids.

3. **Clock — reproduced.** On the unfixed service, the new default-clock test failed at:

   ```text
   >       result = cancel(reservation, reservation.owner)
   E       TypeError: cancel() missing 1 required positional argument: 'now'
   ```

   The old clock test patched `cancelapp.services.datetime`, a symbol the service never reads, so it was tautological; it was deleted. The service now resolves `now = timezone.now() if now is None else now`, and both tests patch `cancelapp.services.timezone`: the default test returns a half-refund time (a different clock would return the full 101), and the explicit test makes the default clock raise if it is read at all.

4. **Inconsistent state — reproduced.** With a `cancelled` reservation and no document, the first red run failed at `with pytest.raises(errors.InconsistentStateError):` with `AttributeError: module 'cancelapp.errors' has no attribute 'InconsistentStateError'`. After adding only the exception class, the same test failed at `cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))` with `cancelapp.models.RefundDocument.DoesNotExist: RefundDocument matching query does not exist.` The service now raises `InconsistentStateError` from that `DoesNotExist`.

5. **Tautological and duplicate tests — reproduced.** `test_spec_three_deliberate_defects_are_defined` asserted only that a dict had three truthy entries, and `test_spec_simulates_document_writing_failure` repeated the failure test without checking rollback. Both were deleted; `pytest --collect-only -q | tail -1` now prints `30 tests collected`. Each remaining spec deliverable has a behavioural test in the table above.

## Assumptions

- Money is stored as integer rials; "rounded down" means integer floor (`// 2`). No `float` is used.
- "Before it starts" is strict: `now == start` is rejected, as the acceptance sample requires.
- Omitting `now` reads `django.utils.timezone.now()` exactly once, after the permission check; a replay ignores the clock and reads the stored `RefundDocument`.
- A `cancelled` reservation without a `RefundDocument` is corrupt state, reported as `InconsistentStateError` rather than leaking `DoesNotExist`.
- Permission is checked before the repeat shortcut; a replay reads the stored `RefundDocument` and ignores the supplied clock, so it still succeeds after the start.
- The owner need not be a manager. A manager must have `is_manager=True` **and** share the reservation's branch; branch is taken from `reservation.branch`, not from the owner's branch.
- Settings read `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD` with the documented defaults; empty port/password (unix-socket fallback) are passed through as empty strings. A real PostgreSQL server is required by the concurrency test (`select_for_update`), so SQLite is deliberately not used; the fallback provides 16.2.
- `ensure_database()` is idempotent and only creates the per-task `task09` database; pytest-django creates `test_task09`. It runs from `conftest.py` before Django's DB setup and can also be invoked as the `ensure_db` step in the Run command.
- The row lock is taken on the reservation inside the existing atomic block, before status/time checks and before the document write. Permission uses the supplied user and the caller's reservation snapshot; those values are immutable during the race.
- ⚠ The no-transaction mutation also removes the row lock because Django forbids a row lock in autocommit mode; this is a mutation-only compromise, not a change to the implementation.

## Unfinished parts

None. The spec asks for a minimal service plus tests, so there is deliberately no view layer, admin, migration file, or extra feature.
