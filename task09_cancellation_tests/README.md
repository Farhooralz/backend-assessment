# Task 9 — Reservation cancellation policy: service + independent tests

A minimal Django service decides the refund for cancelling a `confirmed` reservation: the owner or a manager of the same branch may cancel before the start, and the refund comes from the collected payment. The cancellation and its refund document are written in one database transaction, so a document-write failure rolls everything back. The test suite never reads the wall clock: it injects `now` and an injectable document writer, then checks both inclusive boundaries and every acceptance sample.

## Layout

| Path | Purpose |
| --- | --- |
| `cancelapp/services.py` | `compute_refund` (pure policy) and `cancel` (permission + atomic write) |
| `cancelapp/models.py` | `Branch`, `User`, `Reservation`, `RefundDocument` |
| `cancelapp/errors.py` | Typed rejections (`PermissionDenied`, `ReservationNotCancellable`, `RefundDocumentWriteError`) |
| `tests/` | 26 spec-driven tests: permission, unit, integration, failure, constraints |
| `mutation_check.py` | Applies 3 deliberate defects to a temp copy and reports the failing tests |

## Run command

There is no HTTP or CLI app in this task — the runnable entry point is the service itself. From this folder:

```bash
DJANGO_SETTINGS_MODULE=cancelapp.settings .venv/bin/python -c \
  "import django; django.setup(); from datetime import timedelta; from cancelapp.services import compute_refund; print(compute_refund(101, timedelta(hours=24)))"
```

Measured output: `101`.

## Test commands and measured results

```bash
.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . \
  && .venv/bin/python -m pytest -q
```

- `ruff format .` → `14 files left unchanged`
- `ruff check .` → `All checks passed!`
- `ruff format --check .` → `14 files already formatted`
- `pytest -q` → `26 passed in 0.09s`

Pure-logic coverage gate:

```bash
.venv/bin/python -m pytest -q --cov=cancelapp --cov-report=term-missing
```

Measured output:

```text
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
cancelapp/__init__.py       0      0   100%
cancelapp/errors.py         4      0   100%
cancelapp/models.py        16      0   100%
cancelapp/services.py      39      0   100%
cancelapp/settings.py       8      0   100%
-----------------------------------------------------
TOTAL                      67      0   100%
26 passed in 0.20s
```

Environment: Python 3.14.4, Django 5.2.19, pytest 9.2.0, pytest-django 4.14.0, pytest-cov 7.1.0, pytest-timeout 2.4.0, ruff 0.17.6 — all pinned in `requirements.txt`. The venv is local at `.venv/`.

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
| Use pytest and pytest-django | `pytest.ini`, `tests/` | `test_spec_uses_pytest_django` |
| Permission tests (owner, same-branch manager, others) | `tests/test_permission.py` | `test_spec_same_branch_manager_can_cancel`, `test_spec_other_branch_manager_cannot_cancel`, `test_spec_unrelated_user_cannot_cancel` (plus `test_spec_owner_can_cancel`) |
| Unit tests | `tests/test_unit_policy.py` | 7 `test_spec_*` boundary/rounding tests |
| Integration tests | `tests/test_integration.py` | 11 `test_spec_*` tests against SQLite |
| Failure tests | `tests/test_failure.py` | `test_spec_document_write_failure_rolls_back`, `test_spec_failed_write_leaves_no_repeat_result` |
| Control the clock | `now` parameter on `cancel`; no `datetime.now()` in the service | `test_spec_clock_is_injected_not_read_from_wall` (monkeypatches `services.datetime` to raise) |
| Simulate a document-writing failure | injectable `document_writer` | `test_spec_simulates_document_writing_failure`, `test_spec_document_write_failure_rolls_back` |
| Atomic cancellation + refund document | one `transaction.atomic()` block | `test_spec_cancel_records_cancellation_and_refund_document`, `test_spec_document_write_failure_rolls_back` |
| Repeat returns previous result | replay from `RefundDocument` | `test_spec_repeat_returns_previous_result` (repeat after start still returns 101; one document only) |
| Three deliberate defects, each mapped to a test name | `mutation_check.py` | `test_spec_three_deliberate_defects_are_defined` (table below) |

## Mutation spot-check

`mutation_check.py` copies `cancelapp/`, `tests/`, `pytest.ini` and itself into a temporary directory, applies one defect there, runs the suite, and prints the failing test names. The real implementation is never modified. Command:

```bash
.venv/bin/python mutation_check.py
```

Measured result table:

| Deliberate defect | Failing tests reported |
| --- | --- |
| `>` instead of `>=` at the 24 h boundary | `test_spec_exactly_24h_remaining_returns_101`, `test_spec_at_least_24h_returns_full_amount` (expected: `test_spec_exactly_24h_remaining_returns_101`) — **CAUGHT** |
| Round half up instead of down (`-(-x // 2)`) | `test_spec_24h_plus_one_second_returns_50`, `test_spec_exactly_2h_remaining_returns_50`, `test_spec_24h_plus_one_second_later_returns_half`, `test_spec_exactly_2h_returns_half`, `test_spec_between_2h_and_24h_returns_half`, `test_spec_half_refund_rounds_down_for_odd_amount` (expected: `test_spec_exactly_2h_remaining_returns_50`) — **CAUGHT** |
| Cancel committed before the refund document | `test_spec_document_write_failure_rolls_back`, `test_spec_failed_write_leaves_no_repeat_result` (expected: `test_spec_document_write_failure_rolls_back`) — **CAUGHT** |

The same three defects were also applied manually to the real `services.py`, each confirmed failing and then reverted: `2 failed, 24 passed`; `6 failed, 20 passed`; `2 failed, 24 passed`. After the final revert: `26 passed`.

## Assumptions

- Money is stored as integer rials; "rounded down" means integer floor (`// 2`). No `float` is used.
- "Before it starts" is strict: `now == start` is rejected, as the acceptance sample requires.
- Permission is checked before the repeat shortcut; a replay reads the stored `RefundDocument` and ignores the supplied clock, so it still succeeds after the start.
- The owner need not be a manager. A manager must have `is_manager=True` **and** share the reservation's branch; branch is taken from `reservation.branch`, not from the owner's branch.
- SQLite in-memory is used because this task is pure logic and the spec permits it; no PostgreSQL or Redis is needed.
- One early failure of `test_spec_failed_write_leaves_no_repeat_result` exposed a stale in-memory `status` after a rolled-back transaction. Fixed in production code by writing the refund document before flipping `status`, still inside the same `transaction.atomic()` block. No test was weakened.

## Unfinished parts

None. The spec asks for a minimal service plus tests, so there is deliberately no view layer, admin, migration file, or extra feature.
