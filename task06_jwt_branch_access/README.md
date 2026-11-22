# Task 6 — JWT and branch invoice access

A small Django/DRF API for reading invoices. Login issues a 5-minute access token and a 7-day
refresh token; refresh rotates the token under a row lock and replay of an old refresh kills the
whole session; logout closes only that session, using either the verified access claims or a refresh
token in the body. Every list/detail query is scoped to the caller's *currently active* branch
memberships (or, for customers, to their own invoices), so the original detail-view IDOR is closed.
Failed logins are counted by one atomic Redis Lua script shared by all workers, and both signing
keys fail closed when not supplied by the environment.

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

Measured result from the final gate: `33 files left unchanged`, `All checks passed!`,
`33 files already formatted`, `60 passed`. Collect count from
`.venv/bin/python -m pytest --collect-only -q | tail -1`: `60 tests collected`.
Per-file collect counts: access 12, db setup 2, input validation 3, logging 2, rate limit 12,
sessions 17, settings 6, tokens 6 (total 60). Versions pinned in `requirements.txt` and
installed: Django 5.2.19, DRF 3.16.1, PyJWT 2.15.1, psycopg[binary] 3.2.10, redis 6.4.0,
pytest 8.4.2, pytest-django 4.11.1, pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6.

The root `conftest.py` calls `access.db_utils.ensure_database()` (idempotent, env-driven) before
pytest-django builds `test_task06`; the same function backs `manage.py ensure_db`. Redis is isolated
to DB index `/6` and flushed per test. Only Redis 6.2-era commands are used: the limiter issues a
single `EVAL` (with `INCR`/`EXPIRE` inside the script), the rest uses `GET`, `DEL` and `FLUSHDB`;
there is no separate `INCR`/`EXPIRE` pair in application code.

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

## Unfinished parts

Nothing required by the spec is missing. Out of scope and not implemented: pagination/filters on the
invoice list, a token-introspection endpoint, password reset, HTTPS enforcement, and production
secret storage (keys must be injected from the deployment's secret manager). There is no admin UI
and no Swagger/OpenAPI documentation, as required by the project rules.
