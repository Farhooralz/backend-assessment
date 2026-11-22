# Task 4 — Goods transfer request cycle

A small Django REST Framework API for transferring goods between branches. A destination employee creates a
`draft`, submits it, and the source manager approves or rejects it with a reason. Visibility is scoped by the
actor's live branch and role; lifecycle fields are recorded by the server.

## Run

```bash
cd task04_goods_transfer_api
set -a; . ../.env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Endpoints (Basic or session authentication):

| Method | Path | Effect |
|---|---|---|
| GET | `/api/transfers/` | visible requests, `?status=draft\|submitted\|approved\|rejected`, `?page=N` |
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

Measured on this machine (Python 3.14.4, PostgreSQL 16.2 over a unix socket): **56 passed in 28.39 s**
(last gate run; earlier clean runs took 28.39 s and 29.62 s).
`tests/conftest.py` creates the `task04` database with `psycopg` before pytest-django builds `test_task04`;
no Redis is used.

## Deliverables covered

- **Serializer, Permission, Authentication, ViewSet**: `TransferRequestSerializer`, `TransferActionPermission`,
  `SessionAuthentication` + `BasicAuthentication`, `TransferRequestViewSet` (`ModelViewSet`).
- **State machine**: `draft → submitted → approved | rejected`; invalid transitions and a second decision
  return 409. Business rules live in plain functions in `transfer/services.py` (row locks via
  `select_for_update`), not in views.
- **Filter / status**: `?status=` accepts the four valid values and returns 400 for an unknown value.
- **Pagination with stable ordering**: page size 2 (configurable up to 100, `?page_size=`), ordered by
  `("-created_at", "-id")`; tested across three pages with controlled timestamps.
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

## Unfinished parts

None within this task's scope. Deployment settings, token/JWT auth and notifications were not requested.

## Mutation spot-check (each applied, tested, then reverted)

| # | Deliberate break | Result (real output) |
|---|---|---|
| 1 | Dropped the manager's branch/status visibility filter in `get_queryset` | `8 failed, 48 passed` — includes `test_spec_source_manager_sees_only_sent_requests_for_own_source`, `test_spec_detail_outside_visibility_returns_404[other_manager]`, `test_spec_status_filter` |
| 2 | Made `status` writable and honoured it on create | `2 failed, 54 passed` — `test_spec_status_is_read_only_on_create` (`'approved' != 'draft'`) and the structural test |
| 3 | Skipped writing `decided_by` / `decided_at` in `decide_request` | `3 failed, 53 passed` — sample cycle, reject-with-reason, decision-fields test |
| 4 | Flipped `quantity <= 0` to `quantity < 0` | `1 failed, 55 passed` — `test_spec_quantity_zero_returns_400` (DB check constraint `transfer_quantity_positive` raised `IntegrityError`) |

After reverting all four: **56 passed**.
