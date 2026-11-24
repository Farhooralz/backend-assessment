# Backend Assessment (Python / Django)

Ten independent mini-projects. Requirements: [`docs/TEST_SPEC.md`](docs/TEST_SPEC.md). Working rules: [`AGENTS.md`](AGENTS.md). Live progress: [`docs/STATUS.md`](docs/STATUS.md). Original plan: [`docs/PLAN.md`](docs/PLAN.md).

## Round 4

Final bounded pass: the human's Task 6 fix was confirmed (`SERVE_PUBLIC` removed and an anonymous HTTP
schema test added), Task 4 gained the same HTTP-level schema assertion, all ten source-tree gates were
re-run with `ruff format --check` before `ruff check`, and the documented run/walkthrough commands were
executed against real infrastructure. Two test counts changed: T4 83 → 84 and T6 72 → 73. Only bug/doc
corrections were made; no new features or dependencies. Clean-clone results are reported separately
in the final report.

## Round 3

Scoped follow-up for the reviewer: Swagger/OpenAPI and hand-testable demo seeding for **tasks 4 and 6 only**.
`AGENTS.md` records the exception; no other task was changed. Both tasks expose public `/api/schema/`
and `/api/docs/`, keep every existing endpoint's authentication and permissions unchanged, and ship an
idempotent `seed_demo` command that takes its password from `DEMO_PASSWORD` (or prints one generated
password once). Test-first red proofs, behaviour mutations and copy-paste `curl` walkthroughs are in the
two task READMEs. The orchestrator re-ran all ten gates; real results are below.

## Round 2

Round 2 followed [`docs/ROUND2_BRIEF.md`](docs/ROUND2_BRIEF.md): every reproduced finding was written as a red test first, fixed, mutation-checked with business-logic mutations, and re-gated by the orchestrator. Task 1 stayed frozen. Findings that did not reproduce are documented as such in the relevant task README, with evidence.

## Reproducible setup (verified)

Target Python is **3.12+**; all gates below were run on Python 3.12.16. Each task folder has its own pinned `requirements.txt` and local `.venv`.

Infrastructure for tasks 3–9 is PostgreSQL 16 + Redis. Choose one option:

```bash
# Option A — Docker (if your environment permits it)
cp -n .env.example .env && docker compose up -d

# Option B — no Docker / no root (the committed fallback script writes .env itself)
scripts/local_infra.sh start     # then: scripts/local_infra.sh status
```

Load the env before any task command: `set -a; . ../.env; set +a` (run from inside a task folder). Fallback values include a unix-socket `POSTGRES_HOST` and empty `POSTGRES_PORT`/`POSTGRES_PASSWORD`; pass them through unchanged. Every task that needs a database has an idempotent `ensure_db` command, so the README run commands work on a fresh checkout **before** pytest has ever run.

Every task's test command is the same quality gate: `ruff format . && ruff check . && ruff format --check . && pytest -q`.

| # | Folder | Topic | Status (Round 4) | Run command | Test command |
| --- | --- | --- | --- | --- | --- |
| 1 | `task01_stream_merge` | Lazy k-way merge of event streams | DONE, frozen — 38 tests | `cd task01_stream_merge && .venv/bin/python measure_memory.py` | `cd task01_stream_merge && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 2 | `task02_pricing_engine` | Pricing engine (OOP/SOLID) | DONE — 39 tests | `cd task02_pricing_engine && .venv/bin/python -c "from decimal import Decimal as D; from pricing import QuoteEngine, QuoteContext, HourMultiplier, PercentDiscount, FixedCredit; print(QuoteEngine([HourMultiplier(D('1.5')), PercentDiscount(D('0.10')), FixedCredit(D('200'))]).quote(D('1000'), QuoteContext(10)))"` | `cd task02_pricing_engine && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 3 | `task03_court_report` | Financial report per court (ORM/PostgreSQL) | DONE — 30 tests | `cd task03_court_report && set -a; . ../.env; set +a; DJANGO_SETTINGS_MODULE=court_report.settings .venv/bin/python -m django ensure_db && DJANGO_SETTINGS_MODULE=court_report.settings .venv/bin/python -m django migrate --noinput` | `cd task03_court_report && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 4 | `task04_goods_transfer_api` | Goods transfer API (DRF) | DONE — 84 tests | `cd task04_goods_transfer_api && set -a; . ../.env; set +a; export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo && .venv/bin/python manage.py runserver` | `cd task04_goods_transfer_api && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 5 | `task05_last_seat_reservation` | Last-seat reservation (concurrency) | DONE — 24 tests | `cd task05_last_seat_reservation && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate` | `cd task05_last_seat_reservation && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 6 | `task06_jwt_branch_access` | JWT + branch authorization | DONE — 73 tests | `cd task06_jwt_branch_access && set -a; . ../.env; set +a; export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" JWT_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" DEMO_PASSWORD='<choose-a-demo-password>'; .venv/bin/python -m django ensure_db && .venv/bin/python -m django migrate && .venv/bin/python -m django seed_demo && .venv/bin/python -m django runserver 127.0.0.1:8000 --noreload` | `cd task06_jwt_branch_access && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 7 | `task07_debtors_refactor` | Debtors report refactor | DONE — 39 tests (28 passed, 11 xfailed) | `cd task07_debtors_refactor && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate && .venv/bin/python manage.py check` | `cd task07_debtors_refactor && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 8 | `task08_receipt_outbox` | Reliable receipt dispatch (Celery/Redis) | DONE — 47 tests | `cd task08_receipt_outbox && set -a; . ../.env; set +a; .venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate && .venv/bin/celery -A celery_app worker -l info` | `cd task08_receipt_outbox && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 9 | `task09_cancellation_tests` | Cancellation policy tests (pytest) | DONE — 30 tests | `cd task09_cancellation_tests && set -a; . ../.env; set +a; .venv/bin/python -m cancelapp.db_setup && DJANGO_SETTINGS_MODULE=cancelapp.settings .venv/bin/python -c "import django; django.setup(); from datetime import timedelta; from cancelapp.services import compute_refund; print(compute_refund(101, timedelta(hours=24)))"` | `cd task09_cancellation_tests && set -a; . ../.env; set +a; .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q` |
| 10 | `task10_erp_architecture` | ERP architecture (design doc) | DONE — 75 tests | `cd task10_erp_architecture && .venv/bin/python check_doc.py` | `cd task10_erp_architecture && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q && .venv/bin/python check_doc.py` |

T4 and T6 have no secret fallbacks: export real `DJANGO_SECRET_KEY` (and `JWT_SECRET_KEY` for T6) for serve/manage commands. The test bootstrap generates ephemeral keys only for pytest.

## Round 2 gate verification (source tree)

These are the orchestrator's real gate results on the current `dev` tree, not claims about a fresh clone. Test counts are confirmed with `pytest --collect-only -q | tail -1` in each task folder.

| Task | Ruff | Tests | Extra |
| --- | --- | --- | --- |
| 1 | all clean, 6 files formatted | `38 passed in 3.96s` | `TOTAL 85 stmts, 0 miss, 100%` |
| 2 | all clean, 10 files formatted | `39 passed in 0.03s` | `TOTAL 145 stmts, 0 miss, 100%` |
| 3 | all clean, 20 files formatted | `30 passed in 9.99s` | benchmark header: naive 3382, optimized 4 |
| 4 | all clean, 28 files formatted | `73 passed in 32.84s` | role matrix: `36/73 tests collected` |
| 5 | all clean, 19 files formatted | `24 passed in 0.63s` | real PostgreSQL row-lock races |
| 6 | all clean, 33 files formatted | `60 passed in 19.65s` | real-process Redis rate-limit test |
| 7 | all clean, 18 files formatted | `28 passed, 11 xfailed in 0.43s` | `39 tests collected`; legacy defect run `11 failed` with `--runxfail` |
| 8 | all clean, 20 files formatted | `47 passed in 5.07s` | real Redis broker + attempt history |
| 9 | all clean, 17 files formatted | `30 passed in 0.40s` | `TOTAL 97 stmts, 0 miss, 100%`; mutation checker 3/3 |
| 10 | all clean, 6 files formatted | `75 passed in 0.14s` | `check_doc.py` OK |

## Round 3 gate verification (source tree)

The orchestrator loaded `../.env` and ran the full quality gate in every task folder on the final Round-3
tree. Ruff format, check and format-check were clean for every task; the file count below is from
`ruff format .`. Test counts are confirmed with `pytest --collect-only -q | tail -1`.

| Task | Ruff | Tests | Extra |
| --- | --- | --- | --- |
| 1 | clean, 6 files | `38 passed in 4.06s` | 38 collected; frozen |
| 2 | clean, 10 files | `39 passed in 0.03s` | 39 collected; `TOTAL 145 stmts, 0 miss, 100%` |
| 3 | clean, 20 files | `30 passed in 10.43s` | 30 collected |
| 4 | clean, 30 files | `83 passed in 37.57s` | 83 collected; schema CLI exit 0, 20324 bytes |
| 5 | clean, 19 files | `24 passed in 0.52s` | 24 collected |
| 6 | clean, 36 files | `72 passed in 21.88s` | 72 collected; schema CLI exit 0, 7334 bytes |
| 7 | clean, 18 files | `28 passed, 11 xfailed in 0.40s` | 39 collected |
| 8 | clean, 20 files | `47 passed in 5.06s` | 47 collected |
| 9 | clean, 17 files | `30 passed in 0.31s` | 30 collected; `TOTAL 97 stmts, 0 miss, 100%` |
| 10 | clean, 6 files | `75 passed in 0.14s` | 75 collected; `check_doc.py` OK |

## Round 4 gate verification (source tree)

Final orchestrator sweep after every fix, with `../.env` loaded. Each row ran
`ruff format --check . && ruff check . && pytest -q` in that order; no `ruff format` was run first.
Test counts are confirmed with the collect-only command in each folder.

| Task | Ruff | Tests | Extra |
| --- | --- | --- | --- |
| 1 | clean, 6 files | `38 passed in 4.15s` | 38 collected; `TOTAL 85 stmts, 0 miss, 100%` |
| 2 | clean, 10 files | `39 passed in 0.02s` | 39 collected; `TOTAL 145 stmts, 0 miss, 100%` |
| 3 | clean, 20 files | `30 passed in 9.93s` | 30 collected |
| 4 | clean, 30 files | `84 passed in 37.70s` | 84 collected; live schema paths verified |
| 5 | clean, 19 files | `24 passed in 0.57s` | 24 collected |
| 6 | clean, 36 files | `73 passed in 22.83s` | 73 collected; live schema paths verified |
| 7 | clean, 18 files | `28 passed, 11 xfailed in 0.39s` | 39 collected |
| 8 | clean, 20 files | `47 passed in 5.07s` | 47 collected |
| 9 | clean, 17 files | `30 passed in 0.33s` | 30 collected; `TOTAL 97 stmts, 0 miss, 100%` |
| 10 | clean, 6 files | `75 passed in 0.14s` | 75 collected; `check_doc.py` OK |

Flakiness loops were all green: T5 10/10, T8 10/10, T9 5/5 and T6 rate/sessions 3/3.
Round-1 clean-clone evidence is recorded in [`docs/STATUS.md`](docs/STATUS.md); Round 4 clean-clone
results are reported separately in the final report.

## AI assistance

AI assistance was used. Tests were written from the spec first, run in a red phase, then the smallest implementation was added to turn them green. Every implementation was mutation-checked with deliberate defects and the results recorded in the task README. Every task README lists its assumptions and unfinished parts. Rounds 3 and 4 followed the same test-first, mutation-checked, evidence-based process for the scoped tasks. Task 1 was frozen by `AGENTS.md`; its two stricter input validations were added only because the repository owner explicitly requested them in Round 1.
