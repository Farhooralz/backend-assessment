# Task 6 — JWT and branch invoice access

A small Django/DRF API for reading invoices. Login issues a 5-minute access token and a 7-day
refresh token; refresh rotates the token and replay of an old refresh kills the whole session;
logout closes only that session. Every list/detail query is scoped to the caller's *currently
active* branch memberships (or, for customers, to their own invoices), so the original detail-view
IDOR is closed.

## Run

```bash
cd task06_jwt_branch_access
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ../.env; set +a
export DJANGO_SETTINGS_MODULE=jwtbranch.settings
.venv/bin/python -m django migrate
.venv/bin/python -m django runserver 127.0.0.1:8000
```

Endpoints: `POST /api/token/` (login), `POST /api/token/refresh/`, `POST /api/token/logout/`,
`GET /api/invoices/`, `GET /api/invoices/<id>/`. Send `Authorization: Bearer <access>` on the
protected routes. `JWT_SECRET_KEY` and `DJANGO_SECRET_KEY` come from the environment (dev fallbacks
exist only to make local runs work; set real values in production).

## Test

```bash
cd task06_jwt_branch_access
set -a; . ../.env; set +a
.venv/bin/python -m pytest -q
```

Full quality gate (the exact command run before reporting):

```bash
.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && ( set -a; . ../.env; set +a; .venv/bin/python -m pytest -q )
```

Measured result: `23 files already formatted`, `All checks passed!`, `32 passed in 11.99s`
(collection: `32 tests collected in 0.02s`). Test split: tokens 6, sessions 9, access 10,
rate limit 5, logging 1. Versions installed: Django 5.2.19, DRF 3.16.1, PyJWT 2.15.1,
psycopg 3.3.9, redis-py 5.2.1, pytest 9.2.0, ruff 0.17.6.

The root `conftest.py` creates database `task06` with `psycopg` (tolerating an existing DB) before
pytest-django builds `test_task06`; Redis is isolated to DB index `/6` and flushed per test.
Only Redis 6.2-era commands are used (`INCR`, `EXPIRE`, `GET`, `DEL`, `FLUSHDB`).

## Library choice

**PyJWT** was chosen over SimpleJWT: this API needs only compact JWS issue/verify, explicit
`exp`/`iat`/`jti`/`sid` claims, and an injectable clock for deterministic expiry tests. PyJWT is a
small standalone dependency with no Django-model coupling, and signature verification stays fully
explicit (`algorithms=["HS256"]`). Expiry is checked against a supplied/injected UTC clock, not
wall-clock time inside the library.

## Deliverables mapped to tests

| Spec item | Evidence (test name) |
|---|---|
| Login / refresh / logout endpoints | `test_spec_login_returns_access_and_refresh_tokens`, `test_spec_refresh_returns_new_token_pair`, `test_spec_logout_revokes_session_and_access_token` |
| Access 5 min / refresh 7 days | `test_spec_access_token_lifetime_is_five_minutes`, `test_spec_refresh_token_lifetime_is_seven_days` |
| Refresh rotated after use | `test_spec_refresh_token_is_rotated_after_use`; old jti replay → `test_spec_reuse_of_old_refresh_revokes_session` |
| Logout closes that same session | `test_spec_two_sessions_are_independent` (two sessions, one logout, other still valid) |
| Live membership check each request | `test_spec_membership_checked_live_each_request`, `test_spec_analyst_sees_only_remaining_branch_after_membership_removal` |
| Analyst A+B, remove A → only B | `test_spec_analyst_sees_only_remaining_branch_after_membership_removal` |
| Out-of-scope record → 404 | `test_spec_out_of_scope_detail_returns_404`, `test_spec_get_queryset_is_scoped_for_every_action[detail]` |
| Expired token → 401 (controlled clock) | `test_spec_expired_access_token_returns_401` (monkeypatches `access.tokens.utcnow` to +6 min) |
| 6th failure in 60 s → 429 | `test_spec_sixth_failed_login_returns_429`; counter + 60 s TTL: `test_spec_failed_login_counter_is_stored_in_redis_with_window` |
| JWT library used | `test_spec_uses_jwt_library` (compact JWS, independently decoded with PyJWT) |
| No key/token in logs | `test_spec_no_tokens_or_key_in_logs` (DEBUG-level `caplog` across login, list, refresh, logout) |
| Permission tests list + detail | `test_spec_list_permission_scoped_by_membership`, `test_spec_detail_permission_allows_in_scope`, `test_spec_customer_sees_only_own_invoice` |
| Separation of two sessions | `test_spec_two_sessions_are_independent`, `test_spec_access_token_sid_checked_each_request` |
| Rate limit shared between workers | `test_spec_rate_limit_shared_between_workers` (independent Redis client observes and advances the same counter) |

Measured constants: access TTL 300 s, refresh TTL 604800 s, failure window 60 s, failure limit 5
(the 6th attempt is rejected). Redis key shape: `login_failures:<username>`, counter verified at 5
with a positive TTL ≤ 60 s.

## IDOR note (fixing the risk)

The reviewed version had `get_queryset()` call `visible_invoices(user)` only for `list`, while
`detail` fell back to `Invoice.objects.all()`. That means any authenticated user could request any
invoice primary key — a textbook IDOR. The fix is structural rather than a per-action patch:
`InvoiceViewSet.get_queryset()` now **always** returns `services.visible_invoices(user)` for every
action, and `visible_invoices()` re-reads active `Membership` rows from PostgreSQL on every request.
DRF's `get_object()` uses that same queryset, so an out-of-scope detail lookup raises `DoesNotExist`
and becomes **404**, never 200 or 403 (no existence leak). Customers are matched by
`Invoice.customer = user`, analysts by active analyst memberships; the two sets are OR-ed.

## Assumptions

- An analyst may read **all** invoices of their active analyst branches, including invoices owned by
  customers in those branches. A customer may read **only** invoices where they are `customer` —
  even if that invoice sits in a branch where they hold a customer membership. The fixture puts the
  customer-owned invoice in a third branch so the two rules are unambiguous.
- The JWT `sub` claim is an integer user id; PyJWT 2.15's `verify_sub` check (which requires a string)
  is explicitly disabled while signature, type, and expiry checks remain on.
- Rate limiting counts **failed** logins only; a successful login clears that account's counter. The
  window starts at the first failure (`INCR` then `EXPIRE` once).
- `JWT_SECRET_KEY` / `DJANGO_SECRET_KEY` default to clearly-labelled development values; production
  deployments must supply them via the environment. No token, signing key, or password is logged by
  the application (the only login log line is `login attempt for user <username>`).

## Mutation spot-check

Three deliberate breaks were applied one at a time, the relevant tests run, and each file restored:

1. **Drop the scoping filter** — made `get_queryset()` use `Invoice.objects.all()` for `detail`
   (the original IDOR). Result: `5 failed, 6 passed` in `tests/test_access.py`, including
   `test_spec_out_of_scope_detail_returns_404` (`assert 200 == 404`).
2. **Flip the throttle comparison** — `int(value) >= LIMIT` → `> LIMIT` in `rate_limit.is_limited`.
   Result: `3 failed, 2 passed` in `tests/test_rate_limit.py`, including
   `test_spec_sixth_failed_login_returns_429` (`assert 401 == 429`).
3. **Skip the session-liveness check** — replaced `not session.is_live` with `False` in
   `JWTAuthentication.authenticate`. Result: `3 failed, 6 passed` in `tests/test_sessions.py`,
   including `test_spec_logout_revokes_session_and_access_token` and
   `test_spec_access_token_sid_checked_each_request` (`assert 200 == 401`).

All three were reverted; the final full run is `32 passed`.

## Unfinished parts

Nothing required by the spec is missing. Out of scope and not implemented: pagination/filters on the
invoice list, a token-introspection endpoint, password reset, HTTPS enforcement, and production
secret storage. There is no admin UI and no Swagger/OpenAPI documentation, as required by the
project rules.
