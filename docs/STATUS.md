# Task status

Last updated: 2026-11-22 — wave 1 started.

Infrastructure note: `docker compose up -d` fails with "permission denied while trying to connect to the docker API"; no local PostgreSQL/Redis binaries are installed and neither port is reachable. Tasks needing PostgreSQL/Redis will be marked `BLOCKED: no postgres` when their wave starts.

| Task | Folder | Status | Notes |
| --- | --- | --- | --- |
| 1 | `task01_stream_merge` | DONE | Frozen; do not touch. |
| 2 | `task02_pricing_engine` | DONE | 26 tests pass; coverage 100%; quality gate re-run by orchestrator. |
| 3 | `task03_court_report` | TODO | Wave 2; needs PostgreSQL. |
| 4 | `task04_goods_transfer_api` | TODO | Wave 2; needs PostgreSQL. |
| 5 | `task05_last_seat_reservation` | TODO | Wave 3; needs PostgreSQL + Redis. |
| 6 | `task06_jwt_branch_access` | TODO | Wave 2; needs PostgreSQL + Redis. |
| 7 | `task07_debtors_refactor` | TODO | Wave 2; needs PostgreSQL. |
| 8 | `task08_receipt_outbox` | TODO | Wave 3; needs PostgreSQL + Redis. |
| 9 | `task09_cancellation_tests` | IN_PROGRESS | Wave 1: cancellation policy. |
| 10 | `task10_erp_architecture` | IN_PROGRESS | Wave 1: architecture doc. |
