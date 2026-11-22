# Task status

Last updated: 2026-11-22 — final. All ten tasks DONE, reviewer findings addressed, clean-clone verification green.

Infrastructure note: `docker compose up -d` failed with "permission denied". The no-Docker fallback `scripts/local_infra.sh` is now committed and was verified from a fresh clone: it bootstrapped its own PostgreSQL 16.2 (unix socket) and Redis 6.2, wrote the git-ignored `.env`, and a real `psycopg` query plus `redis.ping()` both succeeded. No `.env` values were printed or committed. Python 3.12.16 (uv-managed) was used for every gate; no Python 3.14 result is claimed.

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

| Task | Folder | Status | Notes |
| --- | --- | --- | --- |
| 1 | `task01_stream_merge` | DONE | 38 tests; 100% coverage; eager validation + key-type error. |
| 2 | `task02_pricing_engine` | DONE | 39 tests; 100% coverage; spec order enforced. |
| 3 | `task03_court_report` | DONE | 19 tests; 4 queries for 50 courts; real EXPLAIN ANALYZE. |
| 4 | `task04_goods_transfer_api` | DONE | 59 tests; role matrix and page size 20. |
| 5 | `task05_last_seat_reservation` | DONE | 21 tests; 20-thread race; 5x concurrency reruns green. |
| 6 | `task06_jwt_branch_access` | DONE | 45 tests; atomic limiter, locked rotation, fail-closed keys. |
| 7 | `task07_debtors_refactor` | DONE | 20 tests; 2 queries for 100 invoices; defect report. |
| 8 | `task08_receipt_outbox` | DONE | 32 tests; lease, broker recovery, real migration. |
| 9 | `task09_cancellation_tests` | DONE | 30 tests; 100% coverage; 3/3 mutations caught. |
| 10 | `task10_erp_architecture` | DONE | 53 doc tests; `check_doc.py` OK. |

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
