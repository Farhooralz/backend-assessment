# Task 4 — Goods transfer request cycle

A small Django REST Framework API for transferring goods between branches. A destination employee creates a
`draft`, submits it, and the source manager approves or rejects it with a reason. Visibility is scoped by the
actor's live branch and role; lifecycle fields are recorded by the server. Business rules live in
`transfer/services.py`; the viewset only maps them to HTTP.

## Run

```bash
cd task04_goods_transfer_api
set -a; . ../.env; set +a
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/python manage.py ensure_db
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

`SECRET_KEY` is required: settings fail closed when `DJANGO_SECRET_KEY` is missing or blank. `ALLOWED_HOSTS`
defaults to `localhost,127.0.0.1` and can be overridden with a comma-separated env value. `ensure_db` calls
`transfer.db_bootstrap.ensure_database()`, the same idempotent helper used by `tests/conftest.py`, so a fresh
checkout works without running the tests first. It reads `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER` and
`POSTGRES_PASSWORD` from the environment; an empty port or password (the local unix-socket fallback) is passed
through unchanged.

Endpoints (Basic or session authentication):

| Method | Path | Effect |
| --- | --- | --- |
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

`pytest_bootstrap.py` (loaded via `addopts = -p pytest_bootstrap`) generates an ephemeral `DJANGO_SECRET_KEY`
before Django imports settings, so the test command needs no key export. It never overwrites a supplied value.
`tests/conftest.py` calls the same `ensure_database()` helper as `manage.py ensure_db` before pytest-django
builds `test_task04`; no Redis is used.

Latest full gate: **73 passed** (`.venv/bin/python -m pytest -q`). Collect counts, reproducible in this folder:

```bash
set -a; . ../.env; set +a
.venv/bin/python -m pytest --collect-only -q | tail -1                       # 73 tests collected
.venv/bin/python -m pytest --collect-only -q -k test_spec_role_matrix | tail -1  # 36/73 tests collected (37 deselected)
```

## Deliverables covered

- **Serializer, Permission, Authentication, ViewSet**: `TransferRequestSerializer`, `TransferActionPermission`,
  `SessionAuthentication` + `BasicAuthentication`, `TransferRequestViewSet` (`ModelViewSet`). Presence is checked
  in `test_spec_serializer_permission_authentication_and_viewset_present`; behaviour is covered by the role
  matrix (401/403/404) and the read-only payload tests.
- **State machine**: `draft → submitted → approved | rejected`; invalid transitions and a second decision
  return 409. Business rules live in plain functions in `transfer/services.py` (row locks via
  `select_for_update`), not in views.
- **Filter / status**: `?status=` accepts the four valid values and returns 400 for an unknown value.
- **Pagination with stable ordering**: production default page size is 20 (configurable up to 100 via
  `?page_size=`), ordered by `("-created_at", "-id")`. `test_spec_default_page_size_is_20` checks the
  unoverridden default; `test_spec_pagination_with_stable_ordering` and
  `test_spec_pagination_with_identical_created_at_stable_order` check distinct and identical timestamps.
- **Server-side decision-maker**: `decided_by` and `decided_at` are read-only and set from `request.user`
  and `timezone.now()`; datetimes are timezone-aware UTC (`USE_TZ = True`).
- **Role-matrix test**: `test_spec_role_matrix` has 6 actors × 6 actions = 36 behavioural cases (verify with
  the collect-only command above). `test_spec_deliverable_role_matrix_counts_36_cases` keeps the delivered count
  honest.
- **Fail-closed configuration**: `DJANGO_SECRET_KEY` has no default; `ALLOWED_HOSTS` is read from the
  environment. Covered by five `runpy`-based tests in `tests/test_settings.py`.
- **Per-request staff lookup**: `staff_for()` caches the `Staff` row on the per-request `request.user` instance,
  so permission, queryset and service layers share one lookup. Covered by
  `tests/test_services.py::test_spec_staff_for_is_cached_per_request`.
- **Reproducible setup**: `transfer/db_bootstrap.py` holds `connect()`, `database_exists()` and the idempotent
  `ensure_database()`; used by both `tests/conftest.py` and `manage.py ensure_db`. Covered by the behavioural
  `test_spec_ensure_database_is_idempotent`.
- **Money**: none in this task; no `float` values are used.

## Assumptions

- ⚠ The spec says "source manager sees only submitted requests". This is read as *requests that have been sent
  for approval* (`submitted`, `approved`, `rejected`), excluding drafts. Decided requests must remain visible so
  a second decision yields 409 rather than 404; this is what the 409 acceptance line requires.
- ⚠ A user without a `Staff` profile is denied by `has_permission`, so every action returns 403 for them,
  including details (the denial happens before queryset visibility is applied).
- A user's branch and role come from `Staff`; an employee may create only for their own destination branch.
  Creators are employees and deciders are source managers, so those sets are disjoint: the API cannot produce a
  request that its creator may decide.
- Out-of-scope records return 404 even for an action the role could not perform; a forbidden action on a
  *visible* record returns 403.
- `reject` takes its reason in the action payload; `status`, `reason`, `created_by`, `decided_by` and all
  timestamps are read-only in the serializer.
- Page size 20 is the default served to clients; smaller pages used to demonstrate ordering are requested
  with `?page_size=2` in tests, never hard-coded into pagination settings.
- `ensure_database()` creates `task04` only when it is absent and returns `True`/`False` for created/already
  present. It connects to the `postgres` maintenance database and never prints or logs credentials.

## Unfinished parts

None within this task's scope. Deployment settings, token/JWT auth and notifications were not requested.

## Round 2 (external-review fixes)

Each finding below was checked against the code before changing anything. Red runs were executed on the pre-fix
tree; the assertion lines are copied verbatim from those runs.

1. **Role matrix did not match the README's 36 cases — reproduced.** Red test
   `tests/test_transfer_api.py::test_spec_deliverable_role_matrix_counts_36_cases`:
   `E       AssertionError: assert 30 == 36`. Fixed by adding the six `no_profile_user` cases (all 403, because
   `has_permission` rejects a staff-less user before the queryset is consulted). The matrix now collects 36
   cases; the count test asserts both 36 and the six-actor set. The old standalone
   `test_spec_no_profile_user_is_forbidden` was deleted as an exact duplicate of the new
   `no_profile_user` list case (rule 12).
2. **Missing authorization tests — not reproduced as defects.** Before any source change, the two requested
   tests (`test_spec_second_employee_of_same_destination_cannot_submit` and
   `test_spec_employee_creating_for_other_destination_returns_403`) were included in the red run alongside the
   new settings/ordering tests; the run ended `6 failed, 4 passed in 1.30s` and both were among the four passes.
   They are kept as regression coverage (the creator check lives in both the permission and the service, and
   the destination check in both the serializer and the service).
3. **Stable ordering with identical `created_at` — not a code defect.** The queryset already had `-id`; the
   missing piece was a test. `test_spec_pagination_with_identical_created_at_stable_order` passed on the pre-fix
   code. Its red proof comes from the first mutation below: `E       assert [2, 1, 3, 4, 5] == [5, 4, 3, 2, 1]`.
4. **Unreachable creator guard in `decide_request` — reproduced as dead code, not a behavioural failure.** No red
   test can be written for code that cannot be reached through the API: `create` requires the employee role and
   `approve`/`reject` require the source-manager role. The guard was removed and the disjoint-role reasoning is
   documented under Assumptions; `test_spec_creator_cannot_decide` still passes. The mock-only tautology test
   `test_spec_ensure_db_command_calls_ensure_database` was deleted; `ensure_database` still has a behavioural
   test (`test_spec_ensure_database_is_idempotent`).
5. **Settings fail-closed, `ALLOWED_HOSTS` from env, `staff_for` caching — all reproduced.** Pre-fix assertion
   lines:
   - `tests/test_settings.py::test_spec_settings_fail_closed_without_secret` — `E       Failed: DID NOT RAISE <class 'django.core.exceptions.ImproperlyConfigured'>`
   - `tests/test_settings.py::test_spec_settings_fail_closed_on_blank_secret` — `E       Failed: DID NOT RAISE <class 'django.core.exceptions.ImproperlyConfigured'>`
   - `tests/test_settings.py::test_spec_settings_allowed_hosts_from_env` — `E       AssertionError: assert ['*'] == ['a.example.c....example.com']`
   - `tests/test_settings.py::test_spec_settings_allowed_hosts_default` — `E       AssertionError: assert ['*'] == ['localhost', '127.0.0.1']`
   - `tests/test_services.py::test_spec_staff_for_is_cached_per_request` — `E       assert 2 == 1`
   
   Fixed with `_required_secret()`, env-driven `ALLOWED_HOSTS`, a test-only key bootstrap, and a cache stored on
   the per-request user object.
6. **Assumption marker — doc-only.** Added ⚠ to the manager-visibility and staff-less-user assumptions; no
   behavioural red test applies to a documentation marker.

## Mutation spot-check (round 2; each applied, tested, then reverted)

All four mutations change business behaviour and name the exact test that fails.

| # | Deliberate break (business logic) | Failing test (`file::test_name`) | Real assertion |
| --- | --- | --- | --- |
| 1 | Drop `-id` from `TransferRequestViewSet.get_queryset().order_by()` | `tests/test_transfer_api.py::test_spec_pagination_with_identical_created_at_stable_order` | `assert [2, 1, 3, 4, 5] == [5, 4, 3, 2, 1]` |
| 2 | Remove the creator check from submit (both the permission object check and `submit_request`'s service check) | `tests/test_transfer_api.py::test_spec_second_employee_of_same_destination_cannot_submit` | `assert 200 == 403` |
| 3 | Remove the destination-branch create check from both `TransferRequestSerializer.validate` and `create_request` | `tests/test_transfer_api.py::test_spec_employee_creating_for_other_destination_returns_403` | `assert 201 == 403` |
| 4 | Skip writing `decided_by` / `decided_at` in `decide_request` | `tests/test_transfer_api.py::test_spec_sample_three_balls_draft_send_approve` | `assert None == 2` |

After reverting all four, the full gate is green: **73 passed**.
