# Task status

Last updated: 2026-11-22 — final.

Infrastructure note: `docker compose up -d` fails with "permission denied while trying to connect to the docker API"; no local PostgreSQL/Redis binaries are installed and neither port is reachable. Per AGENTS.md, tasks needing PostgreSQL/Redis are marked `BLOCKED: no postgres` and no subagent was launched for them.

| Task | Folder | Status | Notes |
| --- | --- | --- | --- |
| 1 | `task01_stream_merge` | DONE | Frozen; 36 tests pass; clean-clone gate green. |
| 2 | `task02_pricing_engine` | DONE | 26 tests pass; coverage 100%; clean-clone gate green. |
| 3 | `task03_court_report` | BLOCKED: no postgres | Wave 2; PostgreSQL unavailable. |
| 4 | `task04_goods_transfer_api` | BLOCKED: no postgres | Wave 2; PostgreSQL unavailable. |
| 5 | `task05_last_seat_reservation` | BLOCKED: no postgres | Wave 3; PostgreSQL + Redis unavailable. |
| 6 | `task06_jwt_branch_access` | BLOCKED: no postgres | Wave 2; PostgreSQL + Redis unavailable. |
| 7 | `task07_debtors_refactor` | BLOCKED: no postgres | Wave 2; PostgreSQL unavailable. |
| 8 | `task08_receipt_outbox` | BLOCKED: no postgres | Wave 3; PostgreSQL + Redis unavailable. |
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
