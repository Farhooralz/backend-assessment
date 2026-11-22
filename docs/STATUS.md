# Task status

Last updated: 2026-11-22 — wave 2 started.

Infrastructure note: `docker compose up -d` failed with "permission denied". The no-Docker fallback was started with `PYTHONPATH=/tmp/pgserver312:/tmp/redislite39 scripts/local_infra.sh start` (only Python 3.14 is installed, so the cp312/cp39 wheels were supplied via `PYTHONPATH`). `scripts/local_infra.sh status` reports PostgreSQL accepting connections and Redis up; a real `psycopg` query returned "PostgreSQL 16.2" and `redis.ping()` returned `True`. `.env` was written by the script. Do not print `.env` values.

| Task | Folder | Status | Notes |
| --- | --- | --- | --- |
| 1 | `task01_stream_merge` | DONE | Frozen; 36 tests pass; clean-clone gate green. |
| 2 | `task02_pricing_engine` | DONE | 26 tests pass; coverage 100%; clean-clone gate green. |
| 3 | `task03_court_report` | DONE | 15 tests pass on PostgreSQL; 4 queries for 50 courts; EXPLAIN ANALYZE recorded; gate re-run by orchestrator. |
| 4 | `task04_goods_transfer_api` | DONE | 56 tests pass on PostgreSQL; full DRF role matrix, state machine and visibility covered; gate re-run by orchestrator. |
| 5 | `task05_last_seat_reservation` | DONE | 18 tests pass on PostgreSQL; 20-thread race yields exactly 3 successes; 5 consecutive concurrency runs green; gate re-run by orchestrator. |
| 6 | `task06_jwt_branch_access` | DONE | 32 tests pass on PostgreSQL + Redis; IDOR, rotation, rate limit and token-log tests covered; gate re-run by orchestrator. |
| 7 | `task07_debtors_refactor` | DONE | 19 tests pass on PostgreSQL; 2 queries for 100 invoices; defect report recorded; gate re-run by orchestrator. |
| 8 | `task08_receipt_outbox` | DONE | 20 tests pass on PostgreSQL + Redis; outbox, claiming, retries and operator retry covered; gate re-run by orchestrator. |
| 9 | `task09_cancellation_tests` | DONE | 26 tests pass; coverage 100%; mutation checker caught all 3 defects; clean-clone gate green. |
| 10 | `task10_erp_architecture` | DONE | 39 doc tests pass; `check_doc.py` passes; clean-clone gate green. |

## Clean-clone verification

Command: `git clone . /tmp/clean-check`, then a fresh `.venv` per task, `pip install -r requirements.txt`, and the task gate. Real tails:

| Task | Ruff | Tests | Coverage / extra |
| --- | --- | --- | --- |
| 1 | `All checks passed!`, `6 files already formatted` | `36 passed in 5.02s` | `ruff==0.17.6` installed separately in the verification venv; task 1 is frozen and its pinned requirements omit ruff. |
| 2 | `All checks passed!`, `9 files already formatted` | `26 passed in 0.04s` | `TOTAL 94 stmts, 0 miss, 100%`; `26 passed in 0.05s`. |
| 9 | `All checks passed!`, `14 files already formatted` | `26 passed in 0.11s` | `TOTAL 67 stmts, 0 miss, 100%`; all 3 `mutation_check.py` defects CAUGHT. |
| 10 | `All checks passed!`, `2 files already formatted` | `39 passed in 0.09s` | `check_doc.py`: all required sections and diagrams present. |
