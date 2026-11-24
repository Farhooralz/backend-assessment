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

Transfer endpoints use Basic or session authentication; docs/schema/login routes are listed too:

| Method | Path | Effect |
| --- | --- | --- |
| GET | `/api/transfers/` | visible requests, `?status=draft\|submitted\|approved\|rejected`, `?page=N`, `?page_size=N` |
| GET | `/api/transfers/{id}/` | detail (404 outside visibility) |
| POST | `/api/transfers/` | create a draft for the caller's own destination |
| POST | `/api/transfers/{id}/submit/` | creator sends the draft |
| POST | `/api/transfers/{id}/approve/` | source manager approves |
| POST | `/api/transfers/{id}/reject/` | source manager rejects; body `{"reason": "..."}` |
| GET | `/api/schema/` | public OpenAPI document (YAML/JSON) |
| GET | `/api/docs/` | public Swagger UI |
| GET | `/api/auth/login/` | DRF session login helper (for Swagger `cookieAuth`) |

The transfer endpoints above keep their existing Basic/session authentication and `TransferActionPermission`;
only the documentation, schema and login-helper routes are public.

## Try it (hand-on walkthrough)

Start the API from the task folder (keep `runserver` running in that terminal):

```bash
cd task04_goods_transfer_api
set -a; . ../.env; set +a
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
# Leave DEMO_PASSWORD unset: seed_demo generates one password and prints it once.
# Alternatively: export DEMO_PASSWORD='<choose-a-demo-password>'
.venv/bin/python manage.py ensure_db
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Open **http://127.0.0.1:8000/api/docs/** (Swagger UI); the raw schema is at
**http://127.0.0.1:8000/api/schema/**. Neither page needs a login. `seed_demo` prints the demo
usernames `demo_employee`, `demo_manager`, `demo_other_employee` and creates 3 branches and 4
requests covering `draft`, `submitted`, `approved` and `rejected`. Running it twice creates no
duplicates (`tests/test_round3_docs_and_seed.py::test_spec_seed_demo_is_idempotent` asserts this).

### Swagger "Authorize" with a demo user

- **Basic:** click **Authorize** → `basicAuth` → username `demo_employee`, password = the value you
  exported as `DEMO_PASSWORD` (or the generated value printed by `seed_demo`). The same password
  works for `demo_manager` and `demo_other_employee`.
- **Session:** open http://127.0.0.1:8000/api/auth/login/ in the same browser, log in as
  `demo_employee` with the demo password, copy the `sessionid` cookie value from browser developer
  tools, then click **Authorize** → `cookieAuth` and paste that value. The login route comes from
  DRF's `rest_framework.urls`; it does not change any transfer endpoint's permission.

### curl walkthrough (expected status codes)

In a second shell (from the same task folder), set `DEMO_PASSWORD` to the value printed by
`seed_demo` (or to the value you exported in the first shell):

```bash
set -a; . ../.env; set +a
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DEMO_PASSWORD='<password-printed-by-seed_demo>'
API=http://127.0.0.1:8000
EMPLOYEE="demo_employee:$DEMO_PASSWORD"
MANAGER="demo_manager:$DEMO_PASSWORD"
OTHER="demo_other_employee:$DEMO_PASSWORD"
SOURCE_ID=$(.venv/bin/python manage.py shell -c "from transfer.models import Branch; print(Branch.objects.get(name='Demo Source').pk)" | tail -1)
DEST_ID=$(.venv/bin/python manage.py shell -c "from transfer.models import Branch; print(Branch.objects.get(name='Demo Destination').pk)" | tail -1)
OTHER_ID=$(.venv/bin/python manage.py shell -c "from transfer.models import Branch; print(Branch.objects.get(name='Demo Other').pk)" | tail -1)

# 1. Employee creates a draft -> HTTP 201, "status":"draft"
curl -s -o /tmp/t04-create.json -w 'create draft: HTTP %{http_code}\n' -u "$EMPLOYEE" \
  -H 'Content-Type: application/json' \
  -d "{\"source\":$SOURCE_ID,\"destination\":$DEST_ID,\"item_name\":\"balls\",\"quantity\":3}" \
  "$API/api/transfers/"
cat /tmp/t04-create.json
ID=$(.venv/bin/python -c "import json; print(json.load(open('/tmp/t04-create.json'))['id'])")

# 2. Employee sends it -> HTTP 200, "status":"submitted"
curl -s -o /tmp/t04-submit.json -w 'submit: HTTP %{http_code}\n' -u "$EMPLOYEE" \
  -X POST "$API/api/transfers/$ID/submit/"
cat /tmp/t04-submit.json

# 3. Forbidden action on a visible record: employee approves -> HTTP 403
curl -s -o /dev/null -w 'employee approve: HTTP %{http_code}\n' -u "$EMPLOYEE" \
  -X POST "$API/api/transfers/$ID/approve/"

# 4. Source manager approves -> HTTP 200, "status":"approved"
curl -s -o /tmp/t04-approve.json -w 'approve: HTTP %{http_code}\n' -u "$MANAGER" \
  -X POST "$API/api/transfers/$ID/approve/"
cat /tmp/t04-approve.json

# 5. Second decision -> HTTP 409
curl -s -o /dev/null -w 'second decision: HTTP %{http_code}\n' -u "$MANAGER" \
  -X POST "$API/api/transfers/$ID/approve/"

# 6. Quantity 0 -> HTTP 400
curl -s -o /dev/null -w 'quantity 0: HTTP %{http_code}\n' -u "$EMPLOYEE" \
  -H 'Content-Type: application/json' \
  -d "{\"source\":$SOURCE_ID,\"destination\":$DEST_ID,\"item_name\":\"balls\",\"quantity\":0}" \
  "$API/api/transfers/"

# 7. Record outside visibility -> HTTP 404 (created by demo_other_employee for Demo Other)
curl -s -o /tmp/t04-foreign.json -w 'foreign create: HTTP %{http_code}\n' -u "$OTHER" \
  -H 'Content-Type: application/json' \
  -d "{\"source\":$SOURCE_ID,\"destination\":$OTHER_ID,\"item_name\":\"balls\",\"quantity\":1}" \
  "$API/api/transfers/"
FOREIGN_ID=$(.venv/bin/python -c "import json; print(json.load(open('/tmp/t04-foreign.json'))['id'])")
curl -s -o /dev/null -w 'outside visibility: HTTP %{http_code}\n' -u "$EMPLOYEE" \
  "$API/api/transfers/$FOREIGN_ID/"
```

Expected labels: `create draft: HTTP 201`, `submit: HTTP 200`, `employee approve: HTTP 403`,
`approve: HTTP 200`, `second decision: HTTP 409`, `quantity 0: HTTP 400`,
`foreign create: HTTP 201`, `outside visibility: HTTP 404`. The same flow is asserted by
`tests/test_round3_docs_and_seed.py::test_spec_seed_demo_supports_the_documented_curl_walkthrough`.

## Test

```bash
cd task04_goods_transfer_api
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q
```

`pytest_bootstrap.py` (loaded via `addopts = -p pytest_bootstrap`) generates an ephemeral `DJANGO_SECRET_KEY`
before Django imports settings, so the test command needs no key export. It never overwrites a supplied value.
`tests/conftest.py` calls the same `ensure_database()` helper as `manage.py ensure_db` before pytest-django
builds `test_task04`; no Redis is used.

Latest full gate: **84 passed** (`.venv/bin/python -m pytest -q`). Collect counts, reproducible in this folder:

```bash
set -a; . ../.env; set +a
.venv/bin/python -m pytest --collect-only -q | tail -1                       # 84 tests collected
.venv/bin/python -m pytest --collect-only -q -k test_spec_role_matrix | tail -1  # 36/84 tests collected (48 deselected)
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
- **Swagger / OpenAPI**: `drf-spectacular==0.30.0` serves a public `/api/schema/` and `/api/docs/`;
  the schema validates with `--validate --fail-on-warn` and documents every transfer endpoint plus
  `/api/schema/`. Covered by `tests/test_round3_docs_and_seed.py::test_spec_schema_generates_without_errors_or_warnings`,
  `::test_spec_documented_paths_include_every_real_endpoint`, `::test_spec_docs_are_public_but_existing_endpoints_still_require_auth`
  and `::test_spec_schema_describes_action_request_bodies`.
- **Demo seed**: `manage.py seed_demo` creates 3 branches, 3 users and 4 requests idempotently;
  passwords come only from `DEMO_PASSWORD` or a one-time generated secret. Covered by the five
  `test_spec_seed_demo_*` tests and `test_spec_session_login_supports_swagger_cookie_auth` in
  `tests/test_round3_docs_and_seed.py`.
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
- ⚠ The Swagger UI page and the DRF session-login helper are UI/support routes, not API resources, so
  drf-spectacular excludes them from the OpenAPI document. All five transfer API paths plus `/api/schema/`
  are documented (`test_spec_documented_paths_include_every_real_endpoint`).
- ⚠ `DEMO_PASSWORD` is used as-is and is never printed. When it is unset, a random password is generated
  **only if a demo user still needs to be created**, printed once, and then reused on later runs; re-running
  `seed_demo` never rotates or prints it again.
- The demo password is shared by the three demo users so the Swagger `Authorize` dialog needs one value.
  Usernames, branch names and seeded item names are stable natural keys; that is what makes the seed idempotent.

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

After reverting all four, the full gate is green: **73 passed** at the end of round 2.

## Round 3 (Swagger/OpenAPI + demo seed)

Red-first proof, captured before any Round-3 implementation change (verbatim pytest lines):

- `tests/test_round3_docs_and_seed.py::test_spec_schema_generates_without_errors_or_warnings`
  — `E       AssertionError: assert 'spectacular' in {'changepassword': 'django.contrib.auth', ...}`
- `tests/test_round3_docs_and_seed.py::test_spec_docs_are_public_but_existing_endpoints_still_require_auth`
  — `E       assert 404 == 200` (the `/api/docs/` line)
- `tests/test_round3_docs_and_seed.py::test_spec_documented_paths_include_every_real_endpoint`
  — `E       assert 404 == 200` (the `/api/schema/` line)
- `tests/test_round3_docs_and_seed.py::test_spec_schema_describes_action_request_bodies`
  — `E       AssertionError: assert {'created_at'...n', 'id', ...} == {'reason'}`
- `tests/test_round3_docs_and_seed.py::test_spec_session_login_supports_swagger_cookie_auth`
  — `E       assert 404 == 200` (the `/api/auth/login/` line)
- Every `test_spec_seed_demo_*` test initially failed with
  `E               django.core.management.base.CommandError: Unknown command: 'seed_demo'`.

The public-docs change did not reproduce any auth regression: `test_spec_docs_are_public_but_existing_endpoints_still_require_auth`
also asserts 401 for list, create and detail, and those assertions passed before the fix. The interactive walkthrough itself
was executed against a live `runserver`; the status labels in "Try it" are the real output.

### Mutation spot-check (round 3; each applied, tested, then reverted)

| # | Deliberate break (behaviour/deliverable) | Failing test (`file::test_name`) | Real assertion |
| --- | --- | --- | --- |
| 1 | Remove the `/api/docs/` route | `tests/test_round3_docs_and_seed.py::test_spec_docs_are_public_but_existing_endpoints_still_require_auth` | `assert 404 == 200` |
| 2 | Change the docs views' permission to `IsAuthenticated` | `tests/test_round3_docs_and_seed.py::test_spec_docs_are_public_but_existing_endpoints_still_require_auth` | `assert 403 == 200` |
| 3 | Always `create()` demo transfer requests instead of `get_or_create()` | `tests/test_round3_docs_and_seed.py::test_spec_seed_demo_is_idempotent` | `assert (3, 3, 3, 8) == (3, 3, 3, 4)` |
| 4 | Print a supplied `DEMO_PASSWORD` | `tests/test_round3_docs_and_seed.py::test_spec_seed_demo_never_prints_a_supplied_password` | `AssertionError: assert 'supplied-demo-secret-42' not in 'Demo user: ...-secret-42\n'` |
| 5 | Drop `@extend_schema(request=RejectSerializer)` from `reject` | `tests/test_round3_docs_and_seed.py::test_spec_schema_describes_action_request_bodies` | `assert {'created_at'...n', 'id', ...} == {'reason'}` |

After reverting all five, the full gate is green: **84 passed**, verified with the commands in "Test" and below:

```bash
set -a; . ../.env; set +a
.venv/bin/python -m ruff format . && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest -q                                              # 84 passed
.venv/bin/python -m pytest --collect-only -q | tail -1                     # 84 tests collected
```

## Round 4

Added `tests/test_round3_docs_and_seed.py::test_spec_served_schema_lists_every_transfer_path_to_anonymous_http_clients`.
It makes an anonymous HTTP `GET /api/schema/?format=json` and asserts every transfer path from
`DOCUMENTED_PATHS` is present; on the current code it passed with `1 passed in 0.29s`. No implementation
change was needed, so there is no new red fix for this task.

The exact "Try it" bash blocks were extracted from this README and run against a real `runserver`:
`create draft: HTTP 201`, `submit: HTTP 200`, `employee approve: HTTP 403`, `approve: HTTP 200`,
`second decision: HTTP 409`, `quantity 0: HTTP 400`, `foreign create: HTTP 201`,
`outside visibility: HTTP 404`. A separate live check returned `docs 200`, `schema 200`,
`protected 401` and listed `/api/schema/`, `/api/transfers/`, `/api/transfers/{id}/`,
`/api/transfers/{id}/approve/`, `/api/transfers/{id}/reject/`, `/api/transfers/{id}/submit/`.
The full gate is now **84 passed**; `pytest --collect-only -q | tail -1` prints `84 tests collected`.
