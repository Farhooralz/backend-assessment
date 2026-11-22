# Backend Assessment (Python / Django)

Ten independent mini-projects. Requirements: [`docs/TEST_SPEC.md`](docs/TEST_SPEC.md). Working rules: [`AGENTS.md`](AGENTS.md). Live progress: [`docs/STATUS.md`](docs/STATUS.md). Plan/tracker: [`docs/PLAN.md`](docs/PLAN.md).

## Reproducible setup (verified)

Target Python is **3.12+**; all gates below were run on Python 3.12.16. Each task folder has its own pinned `requirements.txt` and local `.venv`.

Infrastructure for tasks 3–9 is PostgreSQL 16 + Redis. Choose one option:

```bash
# Option A — Docker
cp -n .env.example .env && docker compose up -d

# Option B — no Docker / no root (the committed fallback script writes .env itself)
scripts/local_infra.sh start     # then: scripts/local_infra.sh status
```

Load the env before any task command: `set -a; . ../.env; set +a` (run from inside a task folder). Fallback values include a unix-socket `POSTGRES_HOST` and empty `POSTGRES_PORT`/`POSTGRES_PASSWORD`; pass them through unchanged. Every task that needs a database has an idempotent `ensure_db` command, so the README run commands work on a fresh checkout **before** pytest has ever run.

Every task's test command is the same quality gate: `ruff format . && ruff check . && ruff format --check . && pytest -q`.

| # | Folder | Topic | Status | Run command | Test command |
| --- | --- | --- | --- | --- | --- |
| 1 | `task01_stream_merge` | Lazy k-way merge of event streams | DONE | `cd task01_stream_merge && .venv/bin/python measure_memory.py` | `cd task01_stream_merge && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 2 | `task02_pricing_engine` | Pricing engine (OOP/SOLID) | DONE | `cd task02_pricing_engine && .venv/bin/python -c "from decimal import Decimal as D; from pricing import QuoteEngine, QuoteContext, HourMultiplier, PercentDiscount, FixedCredit; print(QuoteEngine([HourMultiplier(D('1.5')), PercentDiscount(D('0.10')), FixedCredit(D('200'))]).quote(D('1000'), QuoteContext(10)))"` | `cd task02_pricing_engine && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 3 | `task03_court_report` | Financial report per court (ORM/PostgreSQL) | DONE | `cd task03_court_report && set -a; . ../.env; set +a; DJANGO_SETTINGS_MODULE=court_report.settings .venv/bin/python -m django ensure_db && DJANGO_SETTINGS_MODULE=court_report.settings .venv/bin/python -m django migrate --noinput` | `cd task03_court_report && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 4 | `task04_goods_transfer_api` | Goods transfer API (DRF) | DONE | `cd task04_goods_transfer_api && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate && .venv/bin/python manage.py runserver` | `cd task04_goods_transfer_api && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 5 | `task05_last_seat_reservation` | Last-seat reservation (concurrency) | DONE | `cd task05_last_seat_reservation && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate` | `cd task05_last_seat_reservation && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 6 | `task06_jwt_branch_access` | JWT + branch authorization | DONE | `cd task06_jwt_branch_access && set -a; . ../.env; set +a; export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" JWT_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"; .venv/bin/python -m django ensure_db && .venv/bin/python -m django migrate` | `cd task06_jwt_branch_access && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 7 | `task07_debtors_refactor` | Debtors report refactor | DONE | `cd task07_debtors_refactor && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate && .venv/bin/python manage.py check` | `cd task07_debtors_refactor && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 8 | `task08_receipt_outbox` | Reliable receipt dispatch (Celery/Redis) | DONE | `cd task08_receipt_outbox && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate && .venv/bin/celery -A celery_app worker -l info` | `cd task08_receipt_outbox && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 9 | `task09_cancellation_tests` | Cancellation policy tests (pytest) | DONE | `cd task09_cancellation_tests && set -a; . ../.env; set +a; .venv/bin/python -m cancelapp.db_setup && DJANGO_SETTINGS_MODULE=cancelapp.settings .venv/bin/python -c "import django; django.setup(); from datetime import timedelta; from cancelapp.services import compute_refund; print(compute_refund(101, timedelta(hours=24)))"` | `cd task09_cancellation_tests && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 10 | `task10_erp_architecture` | ERP architecture (design doc) | DONE | `cd task10_erp_architecture && .venv/bin/python check_doc.py` | `cd task10_erp_architecture && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q && .venv/bin/python check_doc.py` |

T6 has no secret fallbacks: export real `DJANGO_SECRET_KEY` and `JWT_SECRET_KEY` for serve/manage commands (the test plugin generates ephemeral keys only for pytest).

## Clean-clone verification

Verified from a fresh `git clone` of commit `f6d4a40` at `/tmp/clean-verify`: the clone bootstrapped **its own** PostgreSQL 16.2 and Redis with the committed `scripts/local_infra.sh start` (the script wrote the git-ignored `.env` — no hand-made env file), then a fresh Python 3.12 venv per task, `pip install -r requirements.txt`, and the gate above.

| Task | Gate | Tests | Extra |
| --- | --- | --- | --- |
| 1 | ruff clean | `38 passed in 4.24s` | coverage 100% (`85` stmts) |
| 2 | ruff clean | `39 passed in 0.05s` | coverage 100% (`145` stmts) |
| 3 | ruff clean | `19 passed in 8.56s` | PostgreSQL 16.2 |
| 4 | ruff clean | `59 passed in 25.21s` | PostgreSQL 16.2 |
| 5 | ruff clean | `21 passed in 0.25s` | 5 consecutive concurrency runs: `4 passed` each (0.23–0.24 s) |
| 6 | ruff clean | `45 passed in 13.61s` | PostgreSQL 16.2 + Redis 6.2 |
| 7 | ruff clean | `20 passed in 0.17s` | 2 queries for 100 invoices |
| 8 | ruff clean | `32 passed in 0.67s` | real migration, Redis 6.2 |
| 9 | ruff clean | `30 passed in 0.15s` | coverage 100% (`90` stmts); mutation checker 3/3 CAUGHT |
| 10 | ruff clean | `53 passed in 0.10s` | `check_doc.py` OK |

Every task gate was also re-run by the orchestrator in the source tree before its commit. Dependency pins are now consistent across tasks (Django 5.2.19, DRF 3.16.1, psycopg 3.2.10, pytest 8.4.2, pytest-django 4.11.1, pytest-cov 7.1.0, pytest-timeout 2.4.0, ruff 0.17.6).

## AI assistance

AI assistance was used. Tests were written from the spec first, run in a red phase, then the smallest implementation was added to turn them green. Every implementation was mutation-checked with deliberate defects and the results recorded in the task README. Every task README lists its assumptions and unfinished parts. Task 1 was frozen by `AGENTS.md`; its two stricter input validations were added only because the repository owner explicitly requested them after review.
