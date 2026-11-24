# Task status

Last updated: 2026-11-24 - ROUND 3 COMPLETE. Round 2 was complete and pushed; the owner requested a
small scoped follow-up: Swagger/OpenAPI plus hand-testable seed data for tasks 4 and 6 only. `AGENTS.md`
now records that exception. Both task subagents finished their red-first, mutation-checked work; the
orchestrator re-ran every gate on the final tree and all ten tasks are green.

Infrastructure note: `docker compose up -d` failed with "permission denied". The no-Docker fallback `scripts/local_infra.sh` is now committed and was verified from a fresh clone: it bootstrapped its own PostgreSQL 16.2 (unix socket) and Redis 6.2, wrote the git-ignored `.env`, and a real `psycopg` query plus `redis.ping()` both succeeded. No `.env` values were printed or committed. Python 3.12.16 (uv-managed) was used for every gate; no Python 3.14 result is claimed.

## Round 3 (final)

- Scope: only `task04_goods_transfer_api` and `task06_jwt_branch_access` changed. Swagger/OpenAPI and demo
  seeding were added there; all other tasks were untouched except the final orchestrator gate sweep.
- T4 DONE. Red phase: `8 failed` (no `spectacular`, 404 docs/schema/login, missing `seed_demo`,
  wrong action request body). Added public `/api/schema/` and `/api/docs/`, Basic/session Swagger auth,
  idempotent `seed_demo`, and a live-status `curl` walkthrough. Five behaviour mutations were caught.
  Orchestrator gate: `30 files left unchanged`, `All checks passed!`, `30 files already formatted`,
  `83 passed in 37.57s`; collect count `83 tests collected`.
- T6 DONE. Red phase: `11 failed, 1 passed` (missing `spectacular`/`seed_demo`, 404 docs, incompatible
  AutoSchema). Added public docs, `@extend_schema` for login/refresh/logout with small serializers, a
  Bearer `OpenApiAuthenticationExtension`, an idempotent two-branch analyst + customer seed, and removed
  the stale no-Swagger README sentence. Four behaviour mutations were caught. Orchestrator gate:
  `36 files left unchanged`, `All checks passed!`, `36 files already formatted`, `72 passed in 21.88s`;
  collect count `72 tests collected`.
- Schema CLI on the final tree: `spectacular --validate --fail-on-warn` exited 0 for both tasks;
  T4 produced 20324 bytes, T6 produced 7334 bytes. Public docs returned 200 unauthenticated while
  existing protected endpoints still returned 401/403.
- Full orchestrator sweep with `../.env` loaded (all gates green): T1 38, T2 39, T3 30, T4 83, T5 24,
  T6 72, T7 28 passed + 11 xfailed (39 collected), T8 47, T9 30, T10 75. T2 and T9 coverage remained
  `TOTAL 145 stmts, 0 miss, 100%` and `TOTAL 97 stmts, 0 miss, 100%`; T10 `check_doc.py` OK.
- Round-3 commits: `93fd4d1` (T4), `94f3eb6` (T6), followed by this root-docs commit.

Review fixes (all test-first, mutation-checked where applicable, gates re-run by the orchestrator):
- T1: eager 64-stream limit and a dedicated mixed-key-type error (explicit owner exception to the freeze rule).
- T2: engine enforces spec policy order; HourMultiplier uses `start_hour`; non-positive multipliers rejected.
- T3: benchmark EXPLAINs the real ORM SQL; `ensure_db` added; admin-UI omission documented as an assumption.
- T4: production pagination default 20; `ensure_db` added.
- T5: distinct connections proven with `pg_backend_pid()`; `ensure_db` added; README's `.infra-venv` reference removed.
- T6: fail-closed secrets; atomic Redis Lua limiter; `select_for_update` refresh rotation; real concurrent-worker tests.
- T7: real initial migration and `ensure_db` added.
- T8: real migration; claim lease; broker-crash recovery; race-safe Fake; barrier; amount validation; failed-state guard.
- T9: PostgreSQL + `select_for_update` cancel; concurrent-cancel test; `ensure_db`; mutation checker updated.
- T10: partial exclusion constraint with `btree_gist`, corrected ERD, bounded staleness, sizing math, multiple SLOs, stronger doc checks.

| Task | Round 1 | Round 2 (fix) | Round 3 | Status |
| --- | --- | --- | --- | --- |
| 1 | DONE | none, frozen | none, frozen | DONE (fuzz-checked externally) |
| 2 | DONE | none | none | DONE |
| 3 | DONE | P0 bug + tests + seed + EXPLAIN | none | DONE (round 2) |
| 4 | DONE | P1 tests/README/settings | Swagger + demo seed | DONE (round 3) |
| 5 | DONE | P1 tests | none | DONE (round 2) |
| 6 | DONE | P1 validation/logout/tests | Swagger + demo seed | DONE (round 3) |
| 7 | DONE | P2 legacy-vs-new proof | none | DONE (round 2) |
| 8 | DONE | P0 bug + P1 tests/observability | none | DONE (round 2) |
| 9 | DONE | P0 test rewrite | none | DONE (round 2) |
| 10 | DONE | P1 design fixes | none | DONE (round 2) |

### Round 2 progress (chronological)

- T9 DONE. Orchestrator gate: `ruff format .` 17 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 17 already formatted, `pytest -q` 30 passed in 0.40s;
  `pytest --collect-only -q | tail -1` 30 tests collected; coverage `TOTAL 97 stmts, 0 miss, 100%`;
  `mutation_check.py` 3/3 CAUGHT. Hand-revert of `cancelapp/services.py` made
  `test_spec_default_clock_is_timezone_now` fail with `TypeError: cancel() missing 1 required
  positional argument: 'now'` and `test_spec_cancelled_without_document_raises_inconsistent_state`
  fail with `RefundDocument.DoesNotExist`; the fixed file was restored and the gate re-run green.
- T8 DONE. Orchestrator gate: `ruff format .` 20 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 20 already formatted, `pytest -q` 47 passed in 5.07s;
  `pytest --collect-only -q | tail -1` 47 tests collected. Hand-revert of `receipts/services.py`
  made `test_spec_pending_row_with_future_next_attempt_is_not_processed_early` fail with
  `assert OutboxMessage.Status.SENT == 'pending'`,
  `test_spec_stale_worker_defer_cannot_overwrite_sent` fail with `assert 'pending' == 'sent'`, and
  `test_spec_crash_reclaim_beyond_max_attempts_fails` fail with
  `assert OutboxMessage.Status.SENT == 'failed'`; the fixed file was restored and the gate re-run green.
  Findings 4, 6 and 8 were documented as "not reproduced as bugs" with evidence in the task README.
- T3 DONE. Orchestrator gate: `ruff format .` 20 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 20 already formatted, `pytest -q` 30 passed in 9.99s;
  `pytest --collect-only -q | tail -1` 30 tests collected. Hand-revert of `reports/services.py` made
  `test_spec_untagged_booking_does_not_add_none_tag` and
  `test_spec_naive_equals_optimized_with_untagged_bookings` fail with
  `TypeError: '<' not supported between instances of 'str' and 'NoneType'`,
  `test_spec_out_of_range_page_clamps` fail with `EmptyPage`, and
  `test_spec_page_size_is_capped_at_100` fail with `assert 120 == 100`; the fixed file was restored
  and the gate re-run green. The benchmark command was re-run and printed
  `=== Query counts: naive 3382 (3382 by formula), optimized 4; courts 20, confirmed bookings in range 1680 ===`.
  Wave A is complete. Wave B (T5, T6, T4, T10) launched.

- T6 DONE. Orchestrator gate: `ruff format .` 33 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 33 already formatted, `pytest -q` 60 passed in 19.65s;
  `pytest --collect-only -q | tail -1` 60 tests collected. Brief items that already worked are documented
  as "not reproduced" with guard tests; the raw-username log leak, malformed-body 500s, logout token
  handling and env/secret settings were fixed. Mutation check: skip logout save →
  `assert None is not None`, drop string check → `assert 401 == 400`, flip limiter `>=` to `>` →
  `assert 200 == 429`.
- T4 DONE. Orchestrator gate: `ruff format .` 28 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 28 already formatted, `pytest -q` 73 passed in 32.84s;
  `pytest --collect-only -q | tail -1` 73 tests collected and the role matrix collects
  `36/73 tests collected (37 deselected)`. The two requested authorization tests already passed, so
  they are documented as "not reproduced" and kept as guards. Mutation check: drop `-id` →
  `assert [2, 1, 3, 4, 5] == [5, 4, 3, 2, 1]`; drop creator check → `assert 200 == 403`; drop
  destination check → `assert 201 == 403`; skip decision-maker write → `assert None == 2`.
- T5 DONE. Orchestrator gate: `ruff format .` 19 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 19 already formatted, `pytest -q` 24 passed in 0.63s;
  `pytest --collect-only -q | tail -1` 24 tests collected. Verified the concurrency helpers open each
  PostgreSQL connection before `barrier.wait()` and keep it open through the PID assertions.
  Rollback and cross-class key race were documented as "not reproduced" with stronger tests;
  `ClassNotFound` (404) and the post-insert seam were added. Mutation check: drop lock → `assert 17 == 3`,
  flip capacity → `DID NOT RAISE ReservationConflict`, drop `atomic()` → `TransactionManagementError`,
  move hook outside `atomic()` → `assert 1 == 0`, drop error mapping → `assert 'DoesNotExist' == 'ClassNotFound'`.
- T10 DONE. Orchestrator gate: `ruff format .` 6 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 6 already formatted, `pytest -q` 75 passed in 0.14s, `check_doc.py` OK;
  `pytest --collect-only -q | tail -1` 75 tests collected. The README now states the unstable
  `ρ = 150 × 0.010 = 1.5`, the Redis `SET NX` fast-fail gate, 1-2 s hot-cache TTL with single-flight
  refresh, inline expiry with B's NEW request, late-payment controls, and the added ERD tables;
  the checker enforces the new rules. All six findings reproduced; five structure mutations caught.
- T7 DONE. Orchestrator gate: `ruff format .` 18 unchanged, `ruff check .` All checks passed!,
  `ruff format --check .` 18 already formatted, `pytest -q` 28 passed, 11 xfailed in 0.43s;
  `pytest --collect-only -q | tail -1` 39 tests collected. Orchestrator red check:
  `pytest -q --runxfail -k 'legacy and defect'` → 11 failed, 28 deselected; `-k services` →
  19 passed, 20 deselected. Happy-path cases pass on both implementations; every `test_spec_defect_*`
  is strict-xfail on legacy and green on services. Four business mutations caught.
- Wave C root files updated: root `README.md` regenerated from real Round-2 gate runs;
  `docs/PLAN.md` and `docs/ENGINEERING_PLAN.md` gained Round 2 notes and dropped stale CI/deploy/frontend/ADR
  claims; `.opencode/commands/review.md` and `verify.md` gained rules 10-16 as checklist items.
  All ten tasks are now DONE for Round 2.

## Clean-clone verification (final)

Command sequence: `git clone . /tmp/clean-verify`, `PATH=<python3.12-shim> scripts/local_infra.sh start` inside the clone (it wrote `.env` and started PostgreSQL 16.2 + Redis), fresh `.venv` per task with Python 3.12.16, `pip install -r requirements.txt`, then the task gate. Real tails:

| Task | Ruff | Tests | Coverage / extra |
| --- | --- | --- | --- |
| 1 | `All checks passed!`, `6 files already formatted` | `38 passed in 4.24s` | `TOTAL 85 stmts, 0 miss, 100%`. |
| 2 | `All checks passed!`, `10 files already formatted` | `39 passed in 0.05s` | `TOTAL 145 stmts, 0 miss, 100%`. |
| 3 | `All checks passed!`, `19 files already formatted` | `19 passed in 8.56s` | PostgreSQL 16.2. |
| 4 | `All checks passed!`, `25 files already formatted` | `59 passed in 25.21s` | PostgreSQL 16.2. |
| 5 | `All checks passed!`, `19 files already formatted` | `21 passed in 0.25s` | Five `4 passed` concurrency runs (0.23–0.24 s). |
| 6 | `All checks passed!`, `31 files already formatted` | `45 passed in 13.61s` | PostgreSQL 16.2 + Redis 6.2. |
| 7 | `All checks passed!`, `18 files already formatted` | `20 passed in 0.17s` | 2 queries for 100 invoices. |
| 8 | `All checks passed!`, `18 files already formatted` | `32 passed in 0.67s` | Real `0001_initial` migration applied. |
| 9 | `All checks passed!`, `17 files already formatted` | `30 passed in 0.15s` | `TOTAL 90 stmts, 0 miss, 100%`; mutation checker 3/3 CAUGHT. |
| 10 | `All checks passed!`, `4 files already formatted` | `53 passed in 0.10s` | `check_doc.py` OK. |

`docs/PLAN.md` tracker is updated. The last "I can explain it" column remains unchecked by design (human interview follow-up). No CI workflow was added because `AGENTS.md` forbids it. No push failures occurred.
