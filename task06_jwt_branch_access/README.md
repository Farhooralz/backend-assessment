# Task 6 — JWT and branch invoice access

A small Django/DRF API for reading invoices. Login issues a 5-minute access token and a 7-day
refresh token; refresh rotates the token under a row lock and replay of an old refresh kills the
whole session; logout closes only that session. Every list/detail query is scoped to the caller's
*currently active* branch memberships (or, for customers, to their own invoices), so the original
detail-view IDOR is closed. Failed logins are counted by one atomic Redis Lua script shared by all
workers, and both signing keys fail closed when not supplied by the environment.

## Run

```bash
cd task06_jwt_branch_access
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ../.env; set +a
export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
export JWT_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
export DJANGO_SETTINGS_MODULE=jwtbranch.settings
.venv/bin/python -m django ensure_db
.venv/bin/python -m django migrate
.venv/bin/python -m django runserver 127.0.0.1:8000
```

`ensure_db` is idempotent: it creates the task's PostgreSQL database (`task06`) via `psycopg` using
the same environment contract as `conftest.py`. Both keys must come from the environment — there is
no development fallback in source, and settings raise `ImproperlyConfigured` naming the missing
variable when either is absent or blank.

Endpoints: `POST /api/token/` (login), `POST /api/token/refresh/`, `POST /api/token/logout/`,
`GET /api/invoices/`, `GET /api/invoices/<id>/`. Send `Authorization: Bearer <access>` on the
protected routes.

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

Measured result from the final gate: `31 files already formatted`, `All checks passed!`,
`45 passed`. Test split: tokens 6, sessions 11, access 11, rate limit 10, logging 1, settings 4,
db setup 2. Versions pinned in `requirements.txt` and installed: Django 5.2.19, DRF 3.16.1,
PyJWT 2.15.1, psycopg[binary] 3.2.10, redis 6.4.0, pytest 8.4.2, pytest-django 4.11.1,
pytest-timeout 2.4.0, pytest-cov 7.1.0, ruff 0.17.6.

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
| Expired token → 401 (controlled clock) | `test_spec_expired_access_token_returns_401` |
| 6th failure in 60 s → 429 | `test_spec_sixth_failed_login_returns_429`, `test_spec_failed_login_counter_is_stored_in_redis_with_window` |
| **Atomic limiter** | `test_spec_record_failure_uses_one_atomic_lua_script` (exactly one `EVAL`, script contains `INCR`+`EXPIRE`), `test_spec_first_failed_login_sets_ttl_atomically`, `test_spec_counter_expires_without_further_process_calls` (key disappears with no further app call), `test_spec_failed_login_does_not_precheck_counter` (no racy read-before-write) |
| **Rate limiting shared between workers** | `test_spec_sixth_failed_login_across_concurrent_workers` (six barrier-released threads, each with its own Redis client: five 401, one 429, shared counter = 6 in Redis) |
| JWT library used | `test_spec_uses_jwt_library` |
| No key/token in logs | `test_spec_no_tokens_or_key_in_logs` |
| Permission tests list + detail | `test_spec_list_permission_scoped_by_membership`, `test_spec_detail_permission_allows_in_scope`, `test_spec_customer_sees_only_own_invoice` |
| Separation of two sessions | `test_spec_two_sessions_are_independent`, `test_spec_access_token_sid_checked_each_request` |
| **Fail-closed configuration** | `test_spec_settings_fail_closed_without_django_secret`, `test_spec_settings_fail_closed_without_jwt_secret`, `test_spec_settings_fail_closed_on_blank_secret`, `test_spec_settings_use_environment_secrets` |
| **Reproducible bootstrap** | `test_spec_ensure_database_is_idempotent`, `test_spec_ensure_db_management_command_is_idempotent` |

Measured constants: access TTL 300 s, refresh TTL 604800 s, failure window 60 s, failure limit 5
(five failures tolerated, the 6th attempt rejected). Redis key shape: `login_failures:<username>`;
the counter and its TTL are set in the same `EVAL`.

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

## Assumptions

- An analyst may read **all** invoices of their active analyst branches, including invoices owned by
  customers in those branches. A customer may read **only** invoices where they are `customer` —
  even if that invoice sits in a branch where they hold a customer membership. The fixture puts the
  customer-owned invoice in a third branch so the two rules are unambiguous.
- The JWT `sub` claim is an integer user id; PyJWT 2.15's `verify_sub` check (which requires a string)
  is explicitly disabled while signature, type, and expiry checks remain on.
- **Fail-closed keys:** `DJANGO_SECRET_KEY` and `JWT_SECRET_KEY` have no defaults. Missing or blank
  values raise `ImproperlyConfigured` at settings import. Test runs use random per-process keys from
  the pytest bootstrap plugin; production/serve commands must export real keys. No token, signing
  key, or password is logged by the application (the only login log line is
  `login attempt for user <username>`).
- **Atomic limiter:** one Redis Lua script increments, arms the 60 s window only on the first hit,
  and returns the counter, so a crash after the call can never leave a TTL-less key and concurrent
  workers cannot interleave a read with the increment. Failed logins are counted; a successful login
  clears the account's history. `is_limited()` remains a read-only guard for correct-password
  logins during an active lockout.
- **Rotation lock:** `refresh()` locks the `LoginSession` row with `select_for_update()` inside
  `transaction.atomic()`. The losing racer sees the already-rotated `jti`, treats it as reuse, and
  revokes the session, so only one concurrent refresh succeeds and the old token cannot be replayed.
- PostgreSQL 16 and Redis 6.2 are the target infrastructure; `EVAL` is available in Redis 6.2.

## Mutation spot-check

Three deliberate breaks were applied one at a time, the relevant tests run, and each file restored:

1. **Drop the rotation lock** — replaced `select_for_update()` with a plain `.get()` in
   `find_session_for_update`. Result: `2 failed, 9 deselected` in `tests/test_sessions.py`:
   `test_spec_refresh_locks_session_row_with_for_update` and
   `test_spec_concurrent_refresh_rotation_has_one_winner` (`assert [200, 200] == [200, 401]`).
2. **Make the limiter non-atomic again** — restored separate `INCR` then `EXPIRE` calls in
   `rate_limit.record_failure`. Result: `1 failed, 2 passed, 7 deselected` in
   `tests/test_rate_limit.py`: `test_spec_record_failure_uses_one_atomic_lua_script`
   (`assert ['INCR', 'EXPIRE'] == ['EVAL']`).
3. **Restore a hard-coded key fallback** — `DJANGO_SECRET_KEY` fell back to a literal again.
   Result: `2 failed, 2 passed` in `tests/test_settings.py`: the "without django secret" and
   "blank secret" fail-closed tests (`DID NOT RAISE <ImproperlyConfigured>`).

All three were reverted; the final full run is `45 passed`.

## Unfinished parts

Nothing required by the spec is missing. Out of scope and not implemented: pagination/filters on the
invoice list, a token-introspection endpoint, password reset, HTTPS enforcement, and production
secret storage (keys must be injected from the deployment's secret manager). There is no admin UI
and no Swagger/OpenAPI documentation, as required by the project rules.
