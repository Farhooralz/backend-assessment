# Task 4 — Goods transfer request cycle

A small Django REST Framework API for transferring goods between branches. A destination employee creates a
`draft`, submits it, and the source manager approves or rejects it with a reason. Visibility is scoped by the
actor's live branch and role; lifecycle fields are recorded by the server.

## Run

```bash
cd task04_goods_transfer_api
set -a; . ../.env; set +a
.venv/bin/python manage.py ensure_db
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

`ensure_db` calls `transfer.db_bootstrap.ensure_database()`, the same idempotent helper used by
`tests/conftest.py`, so a fresh checkout works without running the tests first. It reads `POSTGRES_HOST`,
`POSTGRES_PORT`, `POSTGRES_USER` and `POSTGRES_PASSWORD` from the environment; an empty port or password
(the local unix-socket fallback) is passed through unchanged.

Endpoints (Basic or session authentication):

| Method | Path | Effect |
|---|---|---|
| GET | `/api/transfers/` | visible requests, `?status=draft\|submitted\|approved\|rejected`, `?page=N`, `?page_size=N` |
| GET | `/api/transfers/{id}/` | detail (404 outside visibility) |
| POST | `/api/transfers/` | create a draft for the caller's own destination |
| POST | `/api/transfers/{id}/submit/` | creator sends the draft |
| POST | `/api/transfers/{id}/approve/` | source manager approves |
| POST | `/api/transfers/{id}/reject/` | source manager rejects; body `{"reason": "..."}` |

## Test

```bash
cd task04_goods_transfer_api
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q
```

Measured on this machine (Python 3.12.16, PostgreSQL 16.2 over a unix socket): **59 passed in 27.65 s**
(last gate run; the pre-fix red run showed `1 failed, 1 passed` for the page-size test plus a collection
error for the missing bootstrap module). `tests/conftest.py` calls the same `ensure_database()` helper as
`manage.py ensure_db` before pytest-django builds `test_task04`; no Redis is used.

## Deliverables covered

- **Serializer, Permission, Authentication, ViewSet**: `TransferRequestSerializer`, `TransferActionPermission`,
  `SessionAuthentication` + `BasicAuthentication`, `TransferRequestViewSet` (`ModelViewSet`).
- **State machine**: `draft → submitted → approved | rejected`; invalid transitions and a second decision
  return 409. Business rules live in plain functions in `transfer/services.py` (row locks via
  `select_for_update`), not in views.
- **Filter / status**: `?status=` accepts the four valid values and returns 400 for an unknown value.
- **Pagination with stable ordering**: production default page size is 20 (configurable up to 100 via
  `?page_size=`), ordered by `("-created_at", "-id")`. `test_spec_default_page_size_is_20` checks the
  unoverridden default; `test_spec_pagination_with_stable_ordering` asks for `?page_size=2` explicitly and
  walks three pages.
- **Reproducible setup**: `transfer/db_bootstrap.py` holds `connect()`, `database_exists()` and the idempotent
  `ensure_database()`; both `tests/conftest.py` and the new `manage.py ensure_db` command use it.
  `test_spec_ensure_database_is_idempotent` and `test_spec_ensure_db_command_calls_ensure_database` cover it.
- **Server-side decision-maker**: `decided_by` and `decided_at` are read-only and set from `request.user`
  and `timezone.now()`; datetimes are timezone-aware UTC (`USE_TZ = True`).
- **Role-matrix test**: `test_spec_role_matrix` covers 6 actors × 6 actions × expected codes (36 cases).
- **Money**: none in this task; no `float` values are used.

## Assumptions

- "Source manager sees only submitted requests" is read as *requests that have been sent for approval*
  (`submitted`, `approved`, `rejected`), excluding drafts. Decided requests must remain addressable so a
  second decision yields 409 rather than 404.
- A user's branch and role come from `Staff`; an employee may create only for their own destination branch
  (403 otherwise). A user without a staff profile is forbidden (403).
- Out-of-scope records return 404 even for an action the role could not perform; a forbidden action on a
  *visible* record returns 403.
- `reject` takes its reason in the action payload; `status`, `reason`, `created_by`, `decided_by` and all
  timestamps are read-only in the serializer.
- Page size 20 is the default served to clients; smaller pages used to demonstrate ordering are requested
  with `?page_size=2` in the test, never hard-coded into pagination settings.
- `ensure_database()` creates `task04` only when it is absent and returns `True`/`False` for created/already
  present. It connects to the `postgres` maintenance database and never prints or logs credentials.

## Unfinished parts

None within this task's scope. Deployment settings, token/JWT auth and notifications were not requested.

## Mutation spot-check (each applied, tested, then reverted)

| # | Deliberate break | Result (real output) |
|---|---|---|
| 1 | Dropped the manager's branch/status visibility filter in `get_queryset` | `8 failed, 48 passed` — includes `test_spec_source_manager_sees_only_sent_requests_for_own_source`, `test_spec_detail_outside_visibility_returns_404[other_manager]`, `test_spec_status_filter` |
| 2 | Made `status` writable and honoured it on create | `2 failed, 54 passed` — `test_spec_status_is_read_only_on_create` (`'approved' != 'draft'`) and the structural test |
| 3 | Skipped writing `decided_by` / `decided_at` in `decide_request` | `3 failed, 53 passed` — sample cycle, reject-with-reason, decision-fields test |
| 4 | Flipped `quantity <= 0` to `quantity < 0` | `1 failed, 55 passed` — `test_spec_quantity_zero_returns_400` (DB check constraint `transfer_quantity_positive` raised `IntegrityError`) |
| 5 | Reset `TransferPagination.page_size` to 2 | `1 failed, 56 deselected` — `test_spec_default_page_size_is_20` (`assert 2 == 20`) |
| 6 | Removed `DuplicateDatabase` suppression in `ensure_database()` | pytest aborted at session startup: `psycopg.errors.DuplicateDatabase: database "task04" already exists` |
| 7 | Made the `ensure_db` command a no-op | `1 failed, 1 passed` — `test_spec_ensure_db_command_calls_ensure_database` (`Expected 'ensure_database' to be called once. Called 0 times.`) |

After reverting all seven: **59 passed in 27.65 s**.
