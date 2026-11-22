# Backend Assessment (Python / Django)

Ten independent mini-projects. Requirements: [`docs/TEST_SPEC.md`](docs/TEST_SPEC.md). Working rules: [`AGENTS.md`](AGENTS.md). Live progress: [`docs/STATUS.md`](docs/STATUS.md).

`DONE` means the orchestrator re-ran that task's quality gate itself. `BLOCKED` means the task needs PostgreSQL/Redis, which are unavailable in this environment (`docker compose` permission denied; no local servers).

| # | Folder | Topic | Status | Run command | Test command |
| --- | --- | --- | --- | --- | --- |
| 1 | `task01_stream_merge` | Lazy k-way merge of event streams | DONE | `cd task01_stream_merge && python measure_memory.py` | `cd task01_stream_merge && pytest -q` |
| 2 | `task02_pricing_engine` | Pricing engine (OOP/SOLID) | DONE | `cd task02_pricing_engine && .venv/bin/python -c "from decimal import Decimal as D; from pricing import QuoteEngine, QuoteContext; print(QuoteEngine([]).quote(D('1000'), QuoteContext(10)))"` | `cd task02_pricing_engine && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 3 | `task03_court_report` | Financial report per court (ORM/PostgreSQL) | BLOCKED: no postgres | — | — |
| 4 | `task04_goods_transfer_api` | Goods transfer API (DRF) | BLOCKED: no postgres | — | — |
| 5 | `task05_last_seat_reservation` | Last-seat reservation (concurrency) | BLOCKED: no postgres | — | — |
| 6 | `task06_jwt_branch_access` | JWT + branch authorization | BLOCKED: no postgres | — | — |
| 7 | `task07_debtors_refactor` | Debtors report refactor | BLOCKED: no postgres | — | — |
| 8 | `task08_receipt_outbox` | Reliable receipt dispatch (Celery/Redis) | BLOCKED: no postgres | — | — |
| 9 | `task09_cancellation_tests` | Cancellation policy tests (pytest) | DONE | `cd task09_cancellation_tests && DJANGO_SETTINGS_MODULE=cancelapp.settings .venv/bin/python -c "import django; django.setup(); from datetime import timedelta; from cancelapp.services import compute_refund; print(compute_refund(101, timedelta(hours=24)))"` | `cd task09_cancellation_tests && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 10 | `task10_erp_architecture` | ERP architecture (design doc) | DONE | `cd task10_erp_architecture && .venv/bin/python check_doc.py` | `cd task10_erp_architecture && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |

Each implemented task folder has its own pinned `requirements.txt` and a `README.md` with run command, test command, assumptions, unfinished parts and its mutation/spot-check record.

## AI assistance

AI assistance was used. Tests were generated from the spec first, run in a red phase, then the smallest implementation was written to turn them green. Every implementation was mutation-checked with deliberate defects and the results recorded in the task README. Every task README lists its assumptions; the blocked tasks have no implementation and therefore no task README.
