# Task status

Last updated: 2026-11-22 — wave 1 in progress.

Infrastructure note: `docker compose up -d` fails with "permission denied while trying to connect to the docker API"; no local PostgreSQL/Redis binaries are installed and neither port is reachable. Per AGENTS.md, tasks needing PostgreSQL/Redis are marked `BLOCKED: no postgres` without launching subagents.

| Task | Folder | Status | Notes |
| --- | --- | --- | --- |
| 1 | `task01_stream_merge` | DONE | Frozen; do not touch. |
| 2 | `task02_pricing_engine` | DONE | 26 tests pass; coverage 100%; quality gate re-run by orchestrator. |
| 3 | `task03_court_report` | BLOCKED: no postgres | Wave 2; PostgreSQL unavailable. |
| 4 | `task04_goods_transfer_api` | BLOCKED: no postgres | Wave 2; PostgreSQL unavailable. |
| 5 | `task05_last_seat_reservation` | BLOCKED: no postgres | Wave 3; PostgreSQL + Redis unavailable. |
| 6 | `task06_jwt_branch_access` | BLOCKED: no postgres | Wave 2; PostgreSQL + Redis unavailable. |
| 7 | `task07_debtors_refactor` | BLOCKED: no postgres | Wave 2; PostgreSQL unavailable. |
| 8 | `task08_receipt_outbox` | BLOCKED: no postgres | Wave 3; PostgreSQL + Redis unavailable. |
| 9 | `task09_cancellation_tests` | IN_PROGRESS | Wave 1: cancellation policy. |
| 10 | `task10_erp_architecture` | DONE | 39 doc tests pass; `check_doc.py` passes; gate re-run by orchestrator. |
