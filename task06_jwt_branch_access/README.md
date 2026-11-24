# Task 6 — JWT and branch invoice access

A small Django/DRF API for reading invoices. Login issues a 5-minute access token and a 7-day
refresh token; refresh rotates the token under a row lock and replay of an old refresh kills the
whole session; logout closes only that session, using either the verified access claims or a refresh
token in the body. Every list/detail query is scoped to the caller's *currently active* branch
memberships (or, for customers, to their own invoices), so the original detail-view IDOR is closed.
Failed logins are counted by one atomic Redis Lua script shared by all workers, and both signing
keys fail closed when not supplied by the environment. An OpenAPI document is served at
`/api/schema/` and a public Swagger UI at `/api/docs/`, so the API can be tried by hand.

## Run

```bash
cd task06_jwt_branch_access
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ../.env; set +a
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
export JWT_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
export ALLOWED_HOSTS="localhost,127.0.0.1"
export DJANGO_SETTINGS_MODULE=jwtbranch.settings
.venv/bin/python -m django ensure_db
.venv/bin/python -m django migrate
.venv/bin/python -m django runserver 127.0.0.1:8000
```

`ensure_db` is idempotent: it creates the task's PostgreSQL database (`task06`) via `psycopg` using
the same environment contract as `conftest.py`. Both keys must come from the environment — there is
no development fallback in source. `JWT_SECRET_KEY` must be at least 32 bytes. `ALLOWED_HOSTS` is a
comma-separated environment value (default `localhost,127.0.0.1`); `*` is never hard-coded.

Endpoints: `POST /api/token/` (login), `POST /api/token/refresh/`, `POST /api/token/logout/`,
`GET /api/invoices/`, `GET /api/invoices/<id>/`. Send `Authorization: Bearer <access>` on the
protected routes. Logout also accepts `{"refresh": "<refresh token>"}` when the access token has
expired. Login, refresh and logout all return 400 for a non-object body or a non-string field.
`GET /api/schema/` (OpenAPI YAML/JSON) and `GET /api/docs/` (Swagger UI) are public; all other
routes keep the authentication and permissions above. See **Try it** below.

## Test

```bash
cd task06_jwt_branch_access
set -a; . ../.env; set +a
.venv/bin/python -m pytest -q
```

`pytest_bootstrap.py` (loaded through `addopts = -p pytest_bootstrap`) gives pytest ephemeral
**random** keys before Django settings load, so the exact command above works even when `../.env`
has no keys; keys already exported in the environment are never overwritten. Tests that load
`../.env` therefore keep working and no development key literal exists in source.

Full quality gate (the exact command run before reporting):

```bash
.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && ( set -a; . ../.env; set +a; .venv/bin/python -m pytest -q )
```

Measured result from the final gate: `36 files left unchanged`, `All checks passed!`,
`36 files already formatted`, `72 passed`. Collect count from
`.venv/bin/python -m pytest --collect-only -q | tail -1`: `72 tests collected`.
Versions pinned in `requirements.txt` and installed: Django 5.2.19, DRF 3.16.1,
drf-spectacular 0.30.0, PyJWT 2.15.1, psycopg[binary] 3.2.10, redis 6.4.0, pytest 8.4.2,
pytest-django 4.11.1, pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6.

The root `conftest.py` calls `access.db_utils.ensure_database()` (idempotent, env-driven) before
pytest-django builds `test_task06`; the same function backs `manage.py ensure_db`. Redis is isolated
to DB index `/6` and flushed per test. Only Redis 6.2-era commands are used: the limiter issues a
single `EVAL` (with `INCR`/`EXPIRE` inside the script), the rest uses `GET`, `DEL` and `FLUSHDB`;
there is no separate `INCR`/`EXPIRE` pair in application code.

## Try it

From the repository root, in one shell (keep this shell open: `DEMO_PASSWORD` is used by the curl
walkthrough below and by the seeded users):

```bash
cd task06_jwt_branch_access
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ../.env; set +a
export DJANGO_SETTINGS_MODULE=jwtbranch.settings
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
export JWT_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
export DEMO_PASSWORD='choose-a-demo-password'
.venv/bin/python -m django ensure_db
.venv/bin/python -m django migrate --noinput
.venv/bin/python -m django seed_demo
.venv/bin/python -m django runserver 127.0.0.1:8000 --noreload
```

`seed_demo` is repeatable and prints `demo usernames: demo_analyst, demo_customer`. It uses
`$DEMO_PASSWORD` when set; without it, the command generates a password and prints it once. No
password is stored in the repository or printed when `DEMO_PASSWORD` is set.

Open **http://127.0.0.1:8000/api/docs/** (Swagger UI; the OpenAPI document is at
http://127.0.0.1:8000/api/schema/). Both pages load without login. To use the UI, log in via
`POST /api/token/`, then paste the returned `access` value into the Bearer **Authorize** field
(Swagger UI adds the `Bearer` prefix itself).

Copy-paste walkthrough in a second shell, still with `DEMO_PASSWORD` exported:

```bash
BASE=http://127.0.0.1:8000
PY=.venv/bin/python
curl -s -o /dev/null -w 'docs %{http_code}\n' $BASE/api/docs/                    # 200
curl -s -o /dev/null -w 'schema %{http_code}\n' $BASE/api/schema/                # 200
curl -s -o /dev/null -w 'no auth %{http_code}\n' $BASE/api/invoices/             # 401

curl -s -o /tmp/task06-login.json -w 'login %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"demo_analyst\",\"password\":\"$DEMO_PASSWORD\"}" $BASE/api/token/  # 200
ACCESS=$($PY -c 'import json;print(json.load(open("/tmp/task06-login.json"))["access"])')
REFRESH=$($PY -c 'import json;print(json.load(open("/tmp/task06-login.json"))["refresh"])')
curl -s -o /tmp/task06-list.json -w 'analyst list %{http_code}\n' \
  -H "Authorization: Bearer $ACCESS" $BASE/api/invoices/                        # 200: DEMO-A-1 and DEMO-B-1

curl -s -o /tmp/task06-customer.json -w 'customer login %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"demo_customer\",\"password\":\"$DEMO_PASSWORD\"}" $BASE/api/token/  # 200
CACCESS=$($PY -c 'import json;print(json.load(open("/tmp/task06-customer.json"))["access"])')
curl -s -o /tmp/task06-owned.json -w 'customer list %{http_code}\n' \
  -H "Authorization: Bearer $CACCESS" $BASE/api/invoices/                       # 200: DEMO-CUST-1 only
OUT_ID=$($PY -c 'import json;print(json.load(open("/tmp/task06-owned.json"))[0]["id"])')
curl -s -o /dev/null -w 'outside detail %{http_code}\n' \
  -H "Authorization: Bearer $ACCESS" $BASE/api/invoices/$OUT_ID/                # 404

curl -s -o /tmp/task06-rotated.json -w 'refresh %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"refresh\":\"$REFRESH\"}" $BASE/api/token/refresh/                      # 200: new pair
curl -s -o /dev/null -w 'old refresh %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"refresh\":\"$REFRESH\"}" $BASE/api/token/refresh/                      # 401: reuse kills session

curl -s -o /tmp/task06-fresh.json -w 're-login %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"demo_analyst\",\"password\":\"$DEMO_PASSWORD\"}" $BASE/api/token/  # 200
FRESH=$($PY -c 'import json;print(json.load(open("/tmp/task06-fresh.json"))["access"])')
curl -s -o /dev/null -w 'logout %{http_code}\n' -X POST \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $FRESH" \
  -d '{}' $BASE/api/token/logout/                                               # 204
curl -s -o /dev/null -w 'after logout %{http_code}\n' \
  -H "Authorization: Bearer $FRESH" $BASE/api/invoices/                         # 401: session closed
rm -f /tmp/task06-*.json
```

The old refresh token is rejected with 401 and, as a theft-detection rule, revokes that whole
session; that is why the walkthrough logs in again before testing logout. Status codes above were
checked against a running `runserver` (see Round 3).

## Library choice

**PyJWT** was chosen over SimpleJWT: this API needs only compact JWS issue/verify, explicit
`exp`/`iat`/`jti`/`sid` claims, and an injectable clock for deterministic expiry tests. PyJWT is a
small standalone dependency with no Django-model coupling, and signature verification stays fully
explicit (`algorithms=["HS256"]`). Expiry is checked against a supplied/injected UTC clock, not
wall-clock time inside the library.

## Deliverables mapped to tests

| Spec item / reviewer finding | Evidence (test name) |
|---|---|
| Login / refresh / logout endpoints | `test_spec_login_returns_access_and_refresh_tokens`, `test_spec_refresh_returns_new_token_pair`, `test_spec_logout_revokes_session_and_access_token` |
| Access 5 min / refresh 7 days | `test_spec_access_token_lifetime_is_five_minutes`, `test_spec_refresh_token_lifetime_is_seven_days` |
| Refresh rotated after use | `test_spec_refresh_token_is_rotated_after_use`; old jti replay → `test_spec_reuse_of_old_refresh_revokes_session` |
| **Refresh rotation locked** | `test_spec_refresh_locks_session_row_with_for_update` (SQL contains `FOR UPDATE`), `test_spec_concurrent_refresh_rotation_has_one_winner` (two barrier-released threads: one 200, one 401, old refresh then kills the session) |
| Logout closes that same session | `test_spec_two_sessions_are_independent` |
| Live membership check each request | `test_spec_membership_checked_live_each_request`, `test_spec_analyst_sees_only_remaining_branch_after_membership_removal` |
| Analyst A+B, remove A → only B | `test_spec_analyst_sees_only_remaining_branch_after_membership_removal` |
| Out-of-scope record → 404 | `test_spec_out_of_scope_detail_returns_404`, `test_spec_get_queryset_is_scoped_for_every_action[detail]` |
| Expired token → 401 (controlled clock) | `test_spec_expired_access_token_returns_401`, `test_spec_expired_refresh_token_over_http_returns_401` |
| 6th failure in 60 s → 429 | `test_spec_sixth_failed_login_returns_429`, `test_spec_failed_login_counter_is_stored_in_redis_with_window` |
| **Atomic limiter** | `test_spec_record_failure_uses_one_atomic_lua_script` (exactly one `EVAL`, script contains `INCR`+`EXPIRE`), `test_spec_first_failed_login_sets_ttl_atomically`, `test_spec_counter_expires_without_further_process_calls` (key disappears with no further app call), `test_spec_failed_login_does_not_precheck_counter` (no racy read-before-write) |
| **Rate limiting shared between workers** | `test_spec_sixth_failed_login_across_concurrent_workers` (six barrier-released threads), `test_spec_sixth_failed_login_across_real_processes` (six `multiprocessing` **spawn** processes, each opening PostgreSQL before the barrier, five 401 + one 429 against real Redis) |
| JWT library used | `test_spec_uses_jwt_library` |
| No key/token/username in logs | `test_spec_no_tokens_or_key_in_logs`, `test_spec_raw_username_is_never_logged` |
| Permission tests list + detail | `test_spec_list_permission_scoped_by_membership`, `test_spec_detail_permission_allows_in_scope`, `test_spec_customer_sees_only_own_invoice` |
| Separation of two sessions | `test_spec_two_sessions_are_independent`, `test_spec_access_token_sid_checked_each_request`, `test_spec_refreshing_one_session_leaves_the_other_valid` |
| Wrong token type rejected | `test_spec_wrong_token_type_is_rejected`, `test_spec_refresh_token_used_as_bearer_returns_401` |
| Malformed bodies → 400 | `test_spec_login_rejects_malformed_bodies`, `test_spec_refresh_rejects_malformed_bodies`, `test_spec_logout_rejects_malformed_bodies` |
| Logout with refresh / bad refresh | `test_spec_logout_accepts_refresh_token_in_body`, `test_spec_logout_with_bad_refresh_returns_401[malformed]`, `test_spec_logout_with_bad_refresh_returns_401[expired]` |
| Logout uses verified claims once | `test_spec_logout_does_not_decode_access_token_twice` |
| **Fail-closed configuration** | `test_spec_settings_fail_closed_without_django_secret`, `test_spec_settings_fail_closed_without_jwt_secret`, `test_spec_settings_fail_closed_on_blank_secret`, `test_spec_settings_use_environment_secrets`, `test_spec_settings_reject_short_jwt_secret`, `test_spec_allowed_hosts_comes_from_environment` |
| **Reproducible bootstrap** | `test_spec_ensure_database_is_idempotent`, `test_spec_ensure_db_management_command_is_idempotent` |
| **Public docs, private API** | `test_spec_docs_page_is_reachable_without_login`, `test_spec_protected_endpoint_still_requires_authentication` |
| **Warning-free OpenAPI** | `test_spec_spectacular_validate_reports_no_errors_or_warnings`, `test_spec_openapi_document_lists_every_endpoint`, `test_spec_schema_documents_token_request_and_response_bodies` |
| **Bearer in Swagger Authorize** | `test_spec_schema_advertises_bearer_access_token` |
| **Demo seed** | `test_spec_seed_demo_is_idempotent`, `test_spec_seed_demo_creates_analyst_in_two_branches_and_customer`, `test_spec_seed_demo_uses_env_password`, `test_spec_seed_demo_generated_password_is_printed_once`, `test_spec_seed_demo_prints_demo_usernames` |
| **Walkthrough contract** | `test_spec_seeded_demo_walkthrough_covers_login_scope_refresh_and_logout` |

Measured constants: access TTL 300 s, refresh TTL 604800 s, failure window 60 s, failure limit 5
(five failures tolerated, the 6th attempt rejected), minimum JWT secret 32 bytes. Redis key shape:
`login_failures:<username>`; the counter and its TTL are set in the same `EVAL`.

## IDOR note (fixing the risk)

The reviewed version had `get_queryset()` call `visible_invoices(user)` only for `list`, while
`detail` fell back to `Invoice.objects.all()`. Any authenticated user could therefore request any
invoice primary key — a textbook IDOR. The fix is structural rather than a per-action patch:
`InvoiceViewSet.get_queryset()` now **always** returns `services.visible_invoices(user)` for every
action, and `visible_invoices()` re-reads active `Membership` rows from PostgreSQL on every request.
DRF's `get_object()` uses that same queryset, so an out-of-scope detail lookup raises `DoesNotExist`
and becomes **404**, never 200 or 403 (no existence leak). Customers are matched by
`Invoice.customer = user`, analysts by active analyst memberships; the two sets are OR-ed. This is
covered by both the list and detail permission tests and by the membership-removal test.

## Round 2

### Red-first proof

Command: `set -a; . ../.env; set +a; .venv/bin/python -m pytest -q` against the **unmodified**
Round-1 implementation with the final tests. Result: `11 failed, 49 passed`. Exact
failing lines (shortened only in the log-message string, which embeds a random token):

| Brief item | Test (`file::test_name`) | Failing line |
|---|---|---|
| 1 login body | `tests/test_input_validation.py::test_spec_login_rejects_malformed_bodies` | `assert 500 == 400` |
| 1 refresh body | `tests/test_input_validation.py::test_spec_refresh_rejects_malformed_bodies` | `assert 500 == 400` |
| 1 logout body | `tests/test_input_validation.py::test_spec_logout_rejects_malformed_bodies` | `assert 204 == 400` |
| 3 raw username | `tests/test_logging.py::test_spec_raw_username_is_never_logged` | `AssertionError: assert 'analyst' not in '... login attempt for user analyst ...'` |
| 3 live capture | `tests/test_logging.py::test_spec_no_tokens_or_key_in_logs` | `AssertionError: assert 'login accepted for user id' in '... login attempt for user analyst ...'` |
| 2 refresh logout | `tests/test_sessions.py::test_spec_logout_accepts_refresh_token_in_body` | `assert 401 == 204` |
| 2 bad refresh | `tests/test_sessions.py::test_spec_logout_with_bad_refresh_returns_401[malformed]` / `[expired]` | `assert 204 == 401` |
| 2 second decode | `tests/test_sessions.py::test_spec_logout_does_not_decode_access_token_twice` | `AssertionError: assert 2 == 1` |
| 5 hosts | `tests/test_settings.py::test_spec_allowed_hosts_comes_from_environment` | `AssertionError: assert ['*'] == ['example.com', 'api.example.com']` |
| 5 short key | `tests/test_settings.py::test_spec_settings_reject_short_jwt_secret` | `Failed: DID NOT RAISE <class 'django.core.exceptions.ImproperlyConfigured'>` |

`test_spec_no_tokens_or_key_in_logs` is the one existing test whose live-capture sentinel was
updated (from `login attempt` to `login accepted for user id`) because the spec-required fix removes
that message; its five negative token/key assertions were left untouched. The raw-username leak is
proved independently by `test_spec_raw_username_is_never_logged`.

### Not reproduced

These brief items passed on the unmodified code and were **not** "fixed" — they were added as
behavioural guards and were part of the `49 passed` above:

- `tests/test_sessions.py::test_spec_expired_refresh_token_over_http_returns_401` — the existing
  `decode_token` type/expiry check already returned 401.
- `tests/test_access.py::test_spec_refresh_token_used_as_bearer_returns_401` — `JWTAuthentication`
  already asked for expected type `access`, so a refresh token was rejected.
- `tests/test_sessions.py::test_spec_refreshing_one_session_leaves_the_other_valid` — sessions were
  already isolated by `session_id`; rotation only touched the named row.
- `tests/test_rate_limit.py::test_spec_sixth_failed_login_across_real_processes` — six spawned
  processes already produced five 401 and one 429, so the existing Lua-script counter was already
  process-safe. No limiter logic was changed.
- The "expired/invalid logout token → 401, **never 500**" part did not reproduce as a 500 either:
  the old view ignored the body entirely and returned 204 (`assert 204 == 401`). The new tests now
  guard the refresh-token path where an uncaught `TokenError` would otherwise become a 500.

### Fixes applied

- `access/serializers.py`: `valid_body()` rejects non-mappings, non-string keys/values and missing
  required fields; `views.py` uses it on login, refresh and logout.
- `access/authentication.py`: stores the verified claims on `request.jwt_claims`; `LogoutView` no
  longer decodes the access JWT again.
- `access/views.py`: logout is `AllowAny` with explicit verification — a `refresh` field is decoded
  as a refresh JWT (invalid/expired → 401), otherwise the authentication class verifies the Bearer
  access JWT. `get_authenticate_header()` keeps `AuthenticationFailed` a 401 rather than a 403.
- `access/services.py`: logs the user id after a successful login only; rejected attempts log a
  generic reason. No username, key or token is logged.
- `jwtbranch/settings.py`: `ALLOWED_HOSTS` read from the environment and `JWT_SECRET_KEY`
  rejected when shorter than 32 bytes.

### Trade-offs (spec-conformant, deliberately kept)

- **Refresh reuse revokes the whole session.** Presenting an already-rotated refresh token marks
  the `LoginSession` revoked, so all access and refresh tokens for that login stop working. This is
  the theft-detection rule from the spec: it stops an attacker replaying a stolen token, at the cost
  of logging out the legitimate client too if both race.
- **Per-account throttling allows a 60-second denial of service by a third party.** The Redis key is
  `login_failures:<username>`, so anyone who knows a username can submit five bad passwords and
  lock that account for the 60-second window. The counter is deliberately per account, as specified.
- **A correct password is rejected while locked.** After the fifth failure, even the real user gets
  429 until the window expires (`test_spec_correct_password_rejected_while_locked`); the successful
   login that clears failures cannot be reached. This follows from the specified per-account
  lockout and was not softened.

### Round-2 mutation spot-check

Three business-logic breaks, applied one at a time and reverted. Every row names the exact test
that failed:

| Mutation (behaviour changed) | Failing test | Observed line |
|---|---|---|
| Skip the revocation write in `services.logout()` | `tests/test_sessions.py::test_spec_logout_accepts_refresh_token_in_body` | `assert None is not None` |
| Drop the non-string value check in `serializers.valid_body()` | `tests/test_input_validation.py::test_spec_login_rejects_malformed_bodies` | `assert 401 == 400` |
| Flip `>=` to `>` in `rate_limit.is_limited()` | `tests/test_rate_limit.py::test_spec_correct_password_rejected_while_locked` | `assert 200 == 429` |

Each mutation run reported exactly `1 failed` from `pytest -q <test>`.

All three were reverted; no mutation marker remains in the source.

## Round 3

### Red-first proof

With `drf-spectacular==0.30.0` installed in the venv but settings, URLs, views and management
commands still at their Round-2 state, the new tests were run first:

```bash
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q tests/test_schema_docs.py tests/test_seed_demo.py
```

Result: `11 failed, 1 passed`. Exact failing lines:

| Requirement | Test (`file::test_name`) | Failing line |
|---|---|---|
| Idempotent demo seed (6 tests) | `tests/test_seed_demo.py::test_spec_seed_demo_is_idempotent`, `::test_spec_seed_demo_creates_analyst_in_two_branches_and_customer`, `::test_spec_seed_demo_uses_env_password`, `::test_spec_seed_demo_generated_password_is_printed_once`, `::test_spec_seed_demo_prints_demo_usernames`, `::test_spec_seeded_demo_walkthrough_covers_login_scope_refresh_and_logout` | `django.core.management.base.CommandError: Unknown command: 'seed_demo'` |
| Warning-free schema | `tests/test_schema_docs.py::test_spec_spectacular_validate_reports_no_errors_or_warnings` | `django.core.management.base.CommandError: Unknown command: 'spectacular'` |
| Public Swagger UI | `tests/test_schema_docs.py::test_spec_docs_page_is_reachable_without_login` | `assert 404 == 200` |
| Every endpoint documented | `tests/test_schema_docs.py::test_spec_openapi_document_lists_every_endpoint` | `AssertionError: Incompatible AutoSchema used on View <class 'access.views.InvoiceViewSet'>. Is DRF's DEFAULT_SCHEMA_CLASS pointing to "drf_spectacular.openapi.AutoSchema" or any other drf-spectacular compatible AutoSchema?` |
| Token request/response bodies | `tests/test_schema_docs.py::test_spec_schema_documents_token_request_and_response_bodies` | same `Incompatible AutoSchema` assertion |
| Bearer security scheme | `tests/test_schema_docs.py::test_spec_schema_advertises_bearer_access_token` | same `Incompatible AutoSchema` assertion |

### Not reproduced

`tests/test_schema_docs.py::test_spec_protected_endpoint_still_requires_authentication` was the
`1 passed`: an unauthenticated `GET /api/invoices/` already returned 401 before any change and
still returns 401. It is kept as a regression guard, not presented as a fix. No existing endpoint
permission or authentication class was changed.

Two test-harness mistakes were found after the first green run and corrected in the tests, not in
the API: `manage.py spectacular` accepts `--format=openapi` (YAML) rather than `yaml`, and an old
refresh-token replay deliberately revokes the whole session, so the logout step uses a new login.
Both are recorded as ⚠ assumptions below.

### Fixes applied

- `requirements.txt`: pinned `drf-spectacular==0.30.0`; `jwtbranch/settings.py` registers the app,
  sets `DEFAULT_SCHEMA_CLASS`, adds a Django template backend for Swagger UI, and marks the two
  docs views `AllowAny` only.
- `jwtbranch/urls.py`: `GET /api/schema/` and `GET /api/docs/`.
- `access/serializers.py` + `access/views.py`: request/response serializers and `@extend_schema`
  on login, refresh and logout, removing the "unable to guess serializer" warnings. Round 2 had
  no request serializer classes (only `valid_body()`), so small ones were added for the documented
  bodies; runtime validation still uses the same `valid_body()` checks.
- `access/authentication.py`: `JWTSecurityScheme` describes the existing `JWTAuthentication` as
  HTTP Bearer/JWT for Swagger's Authorize button.
- `access/management/commands/seed_demo.py`: idempotent demo data (two analyst branches, a
  customer whose own invoice sits outside both branches, and invoices for list/detail/404 flows).
  `DEMO_PASSWORD` is read from the environment; when absent a random password is generated and
  printed once. The usernames are always printed; a configured password is never printed.

### Verified numbers and smoke test

- With `DJANGO_SETTINGS_MODULE=jwtbranch.settings` and the two keys exported,
  `set -a; . ../.env; set +a; .venv/bin/python -m django spectacular --validate --fail-on-warn
  --file /tmp/opencode/task06-schema.yaml; echo "exit=$?"; wc -c /tmp/opencode/task06-schema.yaml;
  grep -E '^  /api' /tmp/opencode/task06-schema.yaml` printed `exit=0`, `7334 /tmp/opencode/task06-schema.yaml`
  and no warnings. Paths in that document: `/api/invoices/`,
  `/api/invoices/{id}/`, `/api/schema/`, `/api/token/`, `/api/token/logout/`, `/api/token/refresh/`.
- `.venv/bin/python -m pytest --collect-only -q | tail -1`: `72 tests collected`.
- Actual `curl` run against `runserver 127.0.0.1:8000 --noreload`:
  `docs=200 schema=200 invoices_noauth=401`, `login=200`, `analyst_list=200`, `customer_list=200`,
  `outside_detail=404`, `refresh=200`, `old_refresh_replay=401`, `fresh_login=200`, `logout=204`,
  `after_logout=401`.

### Round-3 mutation spot-check

Four behaviour-changing breaks, applied one at a time and reverted. Every mutation run reported
exactly `1 failed`:

| Mutation (behaviour changed) | Failing test (`file::test_name`) | Observed line |
|---|---|---|
| Drop `@extend_schema` from `LoginView` (schema loses its request/response contract) | `tests/test_schema_docs.py::test_spec_spectacular_validate_reports_no_errors_or_warnings` | `SchemaGenerationError: Failing as requested due to warnings` |
| Require `IsAuthenticated` on the Swagger view | `tests/test_schema_docs.py::test_spec_docs_page_is_reachable_without_login` | `assert 401 == 200` |
| Drop `Q(customer=user)` from `services.visible_invoices()` | `tests/test_seed_demo.py::test_spec_seeded_demo_walkthrough_covers_login_scope_refresh_and_logout` | `assert [] == ['DEMO-CUST-1']` |
| Rename the Bearer security scheme so Swagger cannot find it | `tests/test_schema_docs.py::test_spec_schema_advertises_bearer_access_token` | `KeyError: 'bearerAuth'` |

No mutation marker remains in the source.

## Assumptions

- An analyst may read **all** invoices of their active analyst branches, including invoices owned by
  customers in those branches. A customer may read **only** invoices where they are `customer` —
  even if that invoice sits in a branch where they hold a customer membership. The fixture puts the
  customer-owned invoice in a third branch so the two rules are unambiguous.
- The JWT `sub` claim is an integer user id; PyJWT 2.15's `verify_sub` check (which requires a string)
  is explicitly disabled while signature, type, and expiry checks remain on.
- **Fail-closed keys:** `DJANGO_SECRET_KEY` and `JWT_SECRET_KEY` have no defaults. Missing or blank
  values raise `ImproperlyConfigured` at settings import, and `JWT_SECRET_KEY` must be at least 32
  bytes. Test runs use random per-process keys from the pytest bootstrap plugin; production/serve
  commands must export real keys. `ALLOWED_HOSTS` comes from the environment (default
  `localhost,127.0.0.1`); pytest-django adds `testserver` itself.
- **Logging:** the only login log lines are `login accepted for user id <id>` on success and a
  generic rejection reason on failure. No username, signing key, password or token is logged.
- **Atomic limiter:** one Redis Lua script increments, arms the 60 s window only on the first hit,
  and returns the counter, so a crash after the call can never leave a TTL-less key and concurrent
  workers cannot interleave a read with the increment. Failed logins are counted; a successful login
  clears the account's history. `is_limited()` remains a read-only guard for correct-password
  logins during an active lockout.
- **Rotation lock:** `refresh()` locks the `LoginSession` row with `select_for_update()` inside
  `transaction.atomic()`. The losing racer sees the already-rotated `jti`, treats it as reuse, and
  revokes the session, so only one concurrent refresh succeeds and the old token cannot be replayed.
- ⚠ **Logout by refresh token:** the refresh JWT's signature, type and expiry are verified, and the
  `sid`/`sub` pair must identify the same session, but its `jti` is not compared with the rotated
  value. Any genuine refresh token for that session can close it; logout is idempotent, so a token
  for an already-revoked session is a no-op 204.
- PostgreSQL 16 and Redis 6.2 are the target infrastructure; `EVAL` is available in Redis 6.2.
- The Swagger UI uses drf-spectacular's default CDN distribution of the Swagger assets, so the
  browser needs network access to that CDN; the OpenAPI document itself is served locally.
- The two docs views use `AllowAny` but keep the JWT authentication class so Swagger displays the
  Bearer Authorize control. No API view's authentication or permission classes were changed.
- `seed_demo` only sets passwords when it creates demo users or when `DEMO_PASSWORD` is set. With
  no env var and existing demo users it leaves their stored hashes alone and prints nothing extra,
  which is what makes the generated password appear only once across repeat runs.
- ⚠ **Refresh replay and logout:** reusing a rotated refresh token returns 401 *and* revokes the
  whole session (the specified theft-detection rule). A following logout with the rotated access
  token is therefore correctly 401; the walkthrough logs in again to demonstrate a 204 logout.

## Unfinished parts

Nothing required by the spec is missing. Out of scope and not implemented: pagination/filters on the
invoice list, a token-introspection endpoint, password reset, HTTPS enforcement, and production
secret storage (keys must be injected from the deployment's secret manager). There is no admin UI.
Swagger/OpenAPI documentation is available at `/api/docs/` and `/api/schema/`; both are public,
while every token and invoice route keeps its existing authentication and permissions.
