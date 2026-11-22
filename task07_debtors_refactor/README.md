# Task 7 — Debtors report rebuild

A Django service `ledger.services.debtors(user, branch_id)` returning the cash-desk debtor report as
`[{"id": <invoice id>, "due": <Decimal>}]`. It keeps the original signature and output keys, but
restricts the report to `issued` invoices of the user's authorized active branch, counts only
`settled` payments, keeps positive dues, and returns rows in ascending id order. The verbatim
pre-refactor function is retained in `ledger/legacy.py` solely for regression tests.

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
helper, so manual commands and the test suite bootstrap the database identically. Verified on a
fresh checkout path: `ensure_db` ran twice (`Database task07 is ready.` both times), `check` reported
`System check identified no issues (0 silenced).`, `migrate` applied `ledger.0001_initial`, and the
shell example printed `[]` on the empty database. The service has no HTTP layer; call it from Django
code or a shell as above.

## Test

```bash
cd task07_debtors_refactor
set -a; . ../.env; set +a
.venv/bin/python -m pytest -q
```

With the venv activated, the equivalent command is `pytest -q`. The suite creates `task07` via the
shared helper before pytest-django builds `test_task07`; no Redis is used. Environment measured for
all numbers below: Python 3.12.16, Django 5.2.19, `psycopg[binary]` 3.2.10, pytest 8.4.2,
pytest-django 4.11.1, pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6 (all pinned in
`requirements.txt`). The final gate run was `20 passed in 0.21s`.

## Assumptions

- The `branch_id` argument is the branch being requested. Access is granted only when the user has
  an **active** `Membership` for that exact branch; otherwise the result is empty. This preserves
  the required signature while enforcing "the user's active branch". If a user has several active
  memberships, the requested one is used and the report is still limited to that branch.
- `due` is a `Decimal` with two decimal places; no `float` is used for money.
- One test fixture was corrected, not its expectation: in
  `test_spec_unrelated_payments_do_not_change_due` the second invoice is marked `settled`. With the
  original fixture it was a second valid debtor, so the spec-correct output necessarily contained
  two rows; the test now isolates the intended "unrelated payment" condition.
- The sample invoice id `300` is explicit, not auto-generated; ids otherwise come from PostgreSQL.
- `ensure_database()` connects to the `postgres` maintenance database with `POSTGRES_HOST`,
  `POSTGRES_PORT`, `POSTGRES_USER` and `POSTGRES_PASSWORD` (empty values omitted, documented
  defaults applied). It suppresses only `DuplicateDatabase` and never drops an existing database.
- A `ledger/migrations/0001_initial.py` initial migration was added: the original app had no
  migrations, so `manage.py migrate` created no tables and the README shell example failed even
  after the database existed.

## Unfinished parts

None within the spec scope. There is no view/API, JWT, or deployment code: the task asks for the
function, its contract tests, and the defect report only.

## Defect report (priority order)

Order below is exactly the priority list in `docs/PLAN.md` §2, item T7: (1) no status filter,
(2) no membership/branch authorization, (3) pending payments counted as paid, (4) negative dues
(`!=` vs `>`), (5) N+1 queries, (6) no ordering. Every row names a `test_spec_*` test that fails on
the unfixed implementation.

| # | Defect | Impact | Catching test |
|---|--------|--------|---------------|
| 1 | No invoice status filter — drafts, settled and cancelled invoices leak into the report | Critical: wrong cash-desk figures | `test_spec_defect_1_only_issued_invoices`, `test_spec_acceptance_status_and_other_branch_excluded` |
| 2 | No membership/branch authorization — any `branch_id` can be read | Critical: cross-branch data leak | `test_spec_defect_2_active_membership_required`, `test_spec_defect_2_membership_must_belong_to_user`, `test_spec_defect_2_requested_branch_must_be_authorized` |
| 3 | Pending (and failed) payments are counted as paid, understating debt | High: money not collected | `test_spec_sample_invoice_300_due_180`, `test_spec_defect_3_pending_and_failed_payments_not_counted` |
| 4 | `!=` instead of `> 0` returns negative dues for overpaid invoices | High: nonsensical debt | `test_spec_defect_4_negative_and_zero_due_excluded` |
| 5 | N+1 queries — one query per invoice plus one per payment set | Medium: 101 queries measured for 100 invoices before the fix | `test_spec_defect_5_at_most_three_queries_for_100_invoices` |
| 6 | No ordering — output follows physical row order | Low: unstable report | `test_spec_defect_6_ascending_id_order` |

## Corrected version and evidence

`ledger/services.py` uses one active-membership `exists()` query and one annotated aggregate query:
`Sum("payments__amount", filter=Q(payments__status="settled"))` wrapped in `Coalesce(..., 0)`,
`F("total") - paid`, `due__gt=0`, `order_by("id")`. Complexity is constant in query count (two
queries regardless of invoice count) and linear in returned rows, aggregated in PostgreSQL rather
than in Python.

- Test-first red run (pre-refactor baseline, 19 tests): `11 failed, 8 passed in 0.35s`; query test
  reported `AssertionError: debtors used 101 queries for 100 invoices`, ordering test reported
  `assert [30, 10, 20] == [10, 20, 30]`.
- New bootstrap test red run: `1 error in 0.08s` at collection (`ModuleNotFoundError:
  No module named 'ledger.db_utils'`), then green as `20 passed in 0.23s`.
- Green run after rewrite (Python 3.12): `20 passed in 0.23s`; final gate `20 passed in 0.21s`.
- Query measurement with `CaptureQueriesContext` (temporary print, removed afterwards):
  `MEASURED_QUERIES=2` for 100 invoices under Python 3.12, asserted `0 < count <= 3`.
- Database bootstrap: `test_spec_ensure_database_is_idempotent` calls `ensure_database()` twice and
  asserts exactly one `task07` row in `pg_database`; `manage.py ensure_db` was run twice with no
  error and `manage.py migrate` then created the tables from `0001_initial`.
- Previous correct behavior is pinned by `test_spec_regression_legacy_positive_debt_and_keys`
  (300 − 100 = 200, keys `id`/`due`) and `test_spec_regression_legacy_zero_debt_is_skipped`
  (fully paid invoice excluded), both running against `ledger/legacy.py`.

## Mutation spot-check

Each break was applied under Python 3.12, the suite was run, and the change was reverted:

1. Removed the settled-only filter (`Sum("payments__amount")`) → `2 failed, 18 passed in 0.27s`
   (`test_spec_sample_invoice_300_due_180`, `test_spec_defect_3_pending_and_failed_payments_not_counted`).
2. Flipped membership check to `is_active=False` → `13 failed, 7 passed in 0.27s` (all authorized-report tests).
3. Changed `.order_by("id")` to `.order_by("-id")` → `1 failed, 19 passed in 0.24s`
   (`test_spec_defect_6_ascending_id_order`).
4. Dropped `contextlib.suppress(psycopg.errors.DuplicateDatabase)` from `ensure_database()` → suite
   aborted with `psycopg.errors.DuplicateDatabase: database "task07" already exists` in
   `pytest_configure`.

Final state after reverting all four: `20 passed in 0.21s` (quality gate, all checks passed).
