# Task 7 — Debtors report rebuild

A Django service `ledger.services.debtors(user, branch_id)` returning the cash-desk debtor report as
`[{"id": <invoice id>, "due": <Decimal>}]`. It keeps the original signature and output keys, but
restricts the report to `issued` invoices of the user's authorized active branch, counts only
`settled` payments, keeps positive dues, and returns rows in ascending id order. The verbatim
pre-refactor function is retained in `ledger/legacy.py` so every defect claim can be reproduced
against it (see **Round 2**).

## Run

From this folder, with the shared infrastructure already running:

```bash
set -a; . ../.env; set +a
.venv/bin/python manage.py ensure_db
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c "from ledger.services import debtors; print(debtors(1, 7))"
```

`ensure_db` is idempotent: `ledger.db_utils.ensure_database()` creates `task07` from the shared
`POSTGRES_*` env vars and tolerates an already-existing database. `tests/conftest.py` calls the same
helper, so manual commands and the test suite bootstrap the database identically. `check` prints
`System check identified no issues (0 silenced).`; the empty-database shell example prints `[]`.
The service has no HTTP layer; call it from Django code or a shell as above.

## Test

```bash
cd task07_debtors_refactor
set -a; . ../.env; set +a
.venv/bin/python -m pytest -q
```

With the venv activated, the equivalent command is `pytest -q`. The suite creates `task07` via the
shared helper before pytest-django builds `test_task07`; no Redis is used. Reproducible counts:

| Command | Real result line |
|---|---|
| `.venv/bin/python -m pytest --collect-only -q \| tail -1` | `39 tests collected` |
| `.venv/bin/python -m pytest -q` | `28 passed, 11 xfailed` |
| `.venv/bin/python -m pytest -q -k services` | `19 passed, 20 deselected` |
| `.venv/bin/python -m pytest -q --runxfail -k 'legacy and not defect'` | `8 passed, 31 deselected` |
| `.venv/bin/python -m pytest -q --runxfail -k 'legacy and defect'` | `11 failed, 28 deselected` |

Versions are pinned in `requirements.txt` and reproducible with `.venv/bin/python -m pip list`:
Python 3.12.16, Django 5.2.19, `psycopg[binary]` 3.2.10, pytest 8.4.2, pytest-django 4.11.1,
pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6. Wall-clock durations are omitted because they
vary between runs; the counts above are stable for the pinned versions.

## Assumptions

- The `branch_id` argument is the branch being requested. Access is granted only when the user has
  an **active** `Membership` for that exact branch; otherwise the result is empty. This preserves
  the required signature while enforcing "the user's active branch". If a user has several active
  memberships, the requested one is used and the report is still limited to that branch.
- `due` is a `Decimal` with two decimal places; no `float` is used for money.
- ⚠ The spec's "settled" / "issued" / "active" labels are modeled as `Payment.Status.SETTLED`,
  `Invoice.Status.ISSUED` and `Membership.is_active=True` respectively; the schema ships with
  `ledger/migrations/0001_initial.py`.
- The two characterization tests grant an active Membership so they exercise identical data on both
  implementations; their amount/key assertions are unchanged.
- In `test_spec_defect_1_unrelated_payments_do_not_change_due` the second invoice is `settled`: that
  is precisely what makes `legacy` leak it (defect 1) while `services` correctly excludes it.
- The sample invoice id `300` is explicit, not auto-generated; ids otherwise come from PostgreSQL.
- `ensure_database()` connects to the `postgres` maintenance database with `POSTGRES_HOST`,
  `POSTGRES_PORT`, `POSTGRES_USER` and `POSTGRES_PASSWORD` (empty values omitted, documented
  defaults applied). It suppresses only `DuplicateDatabase` and never drops an existing database.

## Unfinished parts

None within the spec scope. There is no view/API, JWT, or deployment code: the task asks for the
function, its contract tests, and the defect report only.

## Defect report (priority order)

Order below is exactly the priority list in `docs/PLAN.md` §2, item T7: (1) no status filter,
(2) no membership/branch authorization, (3) pending payments counted as paid, (4) negative dues
(`!=` vs `>`), (5) N+1 queries, (6) no ordering. Every row names a `test_spec_*` test that fails on
`legacy` (strict-xfail variant) and passes on `services`.

| # | Defect | Impact | Catching test (legacy variant fails, services variant passes) |
|---|---|---|---|
| 1 | No invoice status filter — drafts, settled and cancelled invoices leak into the report | Critical: wrong cash-desk figures | `test_spec_defect_1_only_issued_invoices`, `test_spec_defect_1_acceptance_status_and_other_branch_excluded`, `test_spec_defect_1_unrelated_payments_do_not_change_due` |
| 2 | No membership/branch authorization — any `branch_id` can be read | Critical: cross-branch data leak | `test_spec_defect_2_active_membership_required`, `test_spec_defect_2_membership_must_belong_to_user`, `test_spec_defect_2_requested_branch_must_be_authorized` |
| 3 | Pending (and failed) payments are counted as paid, understating debt | High: money not collected | `test_spec_defect_3_sample_invoice_300_due_180`, `test_spec_defect_3_pending_and_failed_payments_not_counted` |
| 4 | `!=` instead of `> 0` returns negative dues for overpaid invoices | High: nonsensical debt | `test_spec_defect_4_negative_and_zero_due_excluded` |
| 5 | N+1 queries — one query per invoice plus one per payment set | Medium: `101` queries measured on `legacy` for `100` invoices | `test_spec_defect_5_at_most_three_queries_for_100_invoices` |
| 6 | No ordering — output follows physical row order | Low: unstable report | `test_spec_defect_6_ascending_id_order` |

## Corrected version and evidence

`ledger/services.py` uses one active-membership `exists()` query and one annotated aggregate query:
`Sum("payments__amount", filter=Q(payments__status="settled"))` wrapped in `Coalesce(..., 0)`,
`F("total") - paid`, `due__gt=0`, `order_by("id")`. Query count is constant in the number of
invoices: the services variant of
`test_spec_defect_5_at_most_three_queries_for_100_invoices` asserts the spec bound (`<= 3`) and
the exact optimized count (`== 2`); the legacy variant asserts the spec bound and fails with
`AssertionError: debtors used 101 queries for 100 invoices`.

Previous correct behavior is pinned by two parametrized regression tests that pass on **both**
implementations: `test_spec_regression_positive_debt_and_keys` (invoice total `300`, settled payment
`100`, due `200`, keys `id`/`due`) and `test_spec_regression_zero_debt_is_skipped` (fully paid
invoice excluded). The spec sample is pinned by `test_spec_defect_3_sample_invoice_300_due_180`
(settled `120` + pending `100` → due `180`) and the status/branch acceptance line by
`test_spec_defect_1_acceptance_status_and_other_branch_excluded`.

## Round 2 — red/green defect evidence

### Parameterization

`tests/test_debtors.py` parametrizes every debtors case over `impl in {"legacy", "services"}`.
The `debtors` fixture resolves the name via `IMPL_MODULES` to `ledger.legacy.debtors` or
`ledger.services.debtors`, so the *same test body* runs against both implementations.

- Happy-path / regression cases use `BOTH = ["legacy", "services"]` and must pass on both.
- `test_spec_defect_*` cases use `DEFECT_IMPLS`, where the `legacy` param carries
  `marks=pytest.mark.xfail(strict=True, reason="defect is present in the legacy function")`.
  `strict=True` means a legacy XPASS would fail the suite, so the red evidence cannot silently rot.
- `tests/test_database.py` is not a debtors case and stays unparametrized.

Result: `8` happy-path cases × `2` implementations = `16` passes, `11` defect cases × `2` = `11`
strict xfails (`legacy`) plus `11` passes (`services`), and `1` database bootstrap test: `39`
collected, `28 passed, 11 xfailed`.

### Red — every claimed defect reproduced on the current legacy code

`pytest -q --runxfail -k 'legacy and defect'` neutralises the xfail marks and runs the defect cases
as ordinary tests. Tail: `11 failed, 28 deselected`. Exact failing assertion lines (collected from
that command; invoice ids are deterministic because pytest-django recreates `test_task07`):

| Defect | `legacy` test node | Failing assertion line |
|---|---|---|
| 1 | `tests/test_debtors.py::test_spec_defect_1_only_issued_invoices[legacy]` | `assert [1, 2, 3, 4] == [1]` |
| 1 | `tests/test_debtors.py::test_spec_defect_1_acceptance_status_and_other_branch_excluded[legacy]` | `AssertionError: assert [{'due': Deci...0'), 'id': 8}] == [{'due': Deci...0'), 'id': 5}]` — `Left contains 3 more items, first extra item: {'due': Decimal('300.00'), 'id': 6}` |
| 1 | `tests/test_debtors.py::test_spec_defect_1_unrelated_payments_do_not_change_due[legacy]` | `Left contains one more item: {'due': Decimal('150.00'), 'id': 11}` |
| 2 | `tests/test_debtors.py::test_spec_defect_2_active_membership_required[legacy]` | `AssertionError: assert [{'due': Deci...'), 'id': 12}] == []` |
| 2 | `tests/test_debtors.py::test_spec_defect_2_membership_must_belong_to_user[legacy]` | `AssertionError: assert [{'due': Deci...'), 'id': 13}] == []` |
| 2 | `tests/test_debtors.py::test_spec_defect_2_requested_branch_must_be_authorized[legacy]` | `AssertionError: assert [{'due': Deci...'), 'id': 14}] == []` |
| 3 | `tests/test_debtors.py::test_spec_defect_3_pending_and_failed_payments_not_counted[legacy]` | `At index 0 diff: {'id': 15, 'due': Decimal('150.00')} != {'id': 15, 'due': Decimal('300.00')}` |
| 3 | `tests/test_debtors.py::test_spec_defect_3_sample_invoice_300_due_180[legacy]` | `At index 0 diff: {'id': 300, 'due': Decimal('80.00')} != {'id': 300, 'due': Decimal('180.00')}` |
| 4 | `tests/test_debtors.py::test_spec_defect_4_negative_and_zero_due_excluded[legacy]` | `Left contains one more item: {'due': Decimal('-50.00'), 'id': 16}` |
| 5 | `tests/test_debtors.py::test_spec_defect_5_at_most_three_queries_for_100_invoices[legacy]` | `AssertionError: debtors used 101 queries for 100 invoices` / `assert 101 <= 3` |
| 6 | `tests/test_debtors.py::test_spec_defect_6_ascending_id_order[legacy]` | `assert [30, 10, 20] == [10, 20, 30]` |

**Not reproduced: none.** All six claimed defects failed on `legacy` for the stated reason; no
finding was forced into a fix.

### Green — same tests against the service

`pytest -q` → `28 passed, 11 xfailed`; `pytest -q -k services` → `19 passed, 20 deselected`;
`pytest -q --runxfail -k 'legacy and not defect'` → `8 passed, 31 deselected`. The happy-path cases
therefore pass on both implementations, every defect case passes on `services`, and the only
expected failures are the strict xfails that *are* the red evidence.

### Mutation spot-check (Round 2, business logic in `ledger/services.py`)

Each mutation was applied to the real implementation, `ledger/__pycache__` was removed to avoid
stale bytecode, and `pytest -q --runxfail -k services` was run; the file was then restored (verified
byte-identical). Counts below are the real result lines of that command.

| Mutation (business logic) | Exact failing test(s) | Result line |
|---|---|---|
| Drop the settled-only filter: `Sum("payments__amount", filter=Q(...SETTLED))` → `Sum("payments__amount")` | `tests/test_debtors.py::test_spec_defect_3_pending_and_failed_payments_not_counted[services]`, `tests/test_debtors.py::test_spec_defect_3_sample_invoice_300_due_180[services]` | `2 failed, 17 passed, 20 deselected` |
| Flip membership check: `is_active=True` → `is_active=False` | `tests/test_debtors.py::test_spec_defect_2_active_membership_required[services]` (plus `13` other services tests) | `14 failed, 5 passed, 20 deselected` |
| Reverse ordering: `.order_by("id")` → `.order_by("-id")` | `tests/test_debtors.py::test_spec_defect_6_ascending_id_order[services]` | `1 failed, 18 passed, 20 deselected` |
| Weaken positivity: `.filter(due__gt=ZERO)` → `.filter(due__gte=ZERO)` | `tests/test_debtors.py::test_spec_defect_4_negative_and_zero_due_excluded[services]`, `tests/test_debtors.py::test_spec_regression_zero_debt_is_skipped[services]` | `2 failed, 17 passed, 20 deselected` |

Final state after all reverts: `ruff format . && ruff check . && ruff format --check .` clean,
`pytest -q` → `28 passed, 11 xfailed`.
