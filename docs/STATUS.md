# Task status

Last updated: 2026-11-22 — final, all waves complete.

Infrastructure note: `docker compose up -d` failed with "permission denied". The no-Docker fallback was started with `PYTHONPATH=/tmp/pgserver312:/tmp/redislite39 scripts/local_infra.sh start` (only Python 3.14 is installed, so the cp312/cp39 wheels were supplied via `PYTHONPATH`). `scripts/local_infra.sh status` reports PostgreSQL accepting connections and Redis up; a real `psycopg` query returned "PostgreSQL 16.2" and `redis.ping()` returned `True`. `.env` was written by the script. Do not print `.env` values. Docker permission errors were NOT treated as a blocker.

| Task | Folder | Status | Notes |
| --- | --- | --- | --- |
| 1 | `task01_stream_merge` | DONE | Frozen; 36 tests pass; clean-clone gate green. |
| 2 | `task02_pricing_engine` | DONE | 26 tests pass; coverage 100%; clean-clone gate green. |
| 3 | `task03_court_report` | DONE | 15 tests pass on PostgreSQL; 4 queries for 50 courts; EXPLAIN ANALYZE recorded; clean-clone gate green. |
| 4 | `task04_goods_transfer_api` | DONE | 56 tests pass on PostgreSQL; full DRF role matrix, state machine and visibility covered; clean-clone gate green. |
| 5 | `task05_last_seat_reservation` | DONE | 18 tests pass on PostgreSQL; 20-thread race yields exactly 3 successes; 5 consecutive concurrency runs green; clean-clone gate green. |
| 6 | `task06_jwt_branch_access` | DONE | 32 tests pass on PostgreSQL + Redis; IDOR, rotation, rate limit and token-log tests covered; clean-clone gate green. |
| 7 | `task07_debtors_refactor` | DONE | 19 tests pass on PostgreSQL; 2 queries for 100 invoices; defect report recorded; clean-clone gate green. |
| 8 | `task08_receipt_outbox` | DONE | 20 tests pass on PostgreSQL + Redis; outbox, claiming, retries and operator retry covered; clean-clone gate green. |
| 9 | `task09_cancellation_tests` | DONE | 26 tests pass; coverage 100%; mutation checker caught all 3 defects; clean-clone gate green. |
| 10 | `task10_erp_architecture` | DONE | 39 doc tests pass; `check_doc.py` passes; clean-clone gate green. |

## Clean-clone verification

Command: `git clone . /tmp/clean-check-final`, copy the gitignored `.env` into the clone, then a fresh `.venv` per task, `pip install -r requirements.txt`, and the task gate (`ruff format . && ruff check . && ruff format --check . && pytest -q`; tasks 3–8 load `../.env` first). Real tails from this run:

| Task | Ruff | Tests | Coverage / extra |
| --- | --- | --- | --- |
| 1 | `All checks passed!`, `6 files already formatted` | `36 passed in 2.29s` | `ruff==0.17.6` installed separately in the verification venv; task 1 is frozen and its pinned requirements omit ruff. |
| 2 | `All checks passed!`, `9 files already formatted` | `26 passed in 0.04s` | `TOTAL 94 stmts, 0 miss, 100%`; `26 passed in 0.05s`. |
| 3 | `All checks passed!`, `16 files already formatted` | `15 passed in 9.74s` | PostgreSQL 16.2. |
| 4 | `All checks passed!`, `20 files already formatted` | `56 passed in 29.33s` | PostgreSQL 16.2. |
| 5 | `All checks passed!`, `15 files already formatted` | `18 passed in 0.44s` | PostgreSQL 16.2; 20-thread race + 5x concurrency reruns also green in the source tree. |
| 6 | `All checks passed!`, `24 files already formatted` | `32 passed in 11.21s` | PostgreSQL 16.2 + Redis 6.2. |
| 7 | `All checks passed!`, `11 files already formatted` | `19 passed in 0.26s` | PostgreSQL 16.2. |
| 8 | `All checks passed!`, `14 files already formatted` | `20 passed in 1.69s` | PostgreSQL 16.2 + Redis 6.2. |
| 9 | `All checks passed!`, `14 files already formatted` | `26 passed in 0.10s` | `TOTAL 67 stmts, 0 miss, 100%`; all 3 `mutation_check.py` defects CAUGHT. |
| 10 | `All checks passed!`, `2 files already formatted` | `39 passed in 0.09s` | `check_doc.py`: all required sections and diagrams present. |

Every DONE task's quality gate was also re-run by the orchestrator in the source tree before its commit. No push failures occurred.
