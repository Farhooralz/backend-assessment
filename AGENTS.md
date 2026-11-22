# AGENTS.md: rules for the coding agent (OpenCode)
 
You are helping build a hiring-test project: ten independent mini-projects (9 code, 1 design doc) for a Backend Engineer role (Python/Django). The human reviews and commits everything. Correctness, clarity and tests matter more than cleverness.
 
## Read first, and only what you need
- Requirements: `docs/TEST_SPEC.md`. Read **only the section of the task you are working on**. If this file and the spec disagree, **the spec wins**.
- Process and standards: `docs/ENGINEERING_PLAN.md` (skim the sections "Quality gates" and "Per-task approach").
- Do not load other tasks' folders.
## Non-negotiable rules
1. **Tests are the contract.** The files under `taskNN_*/tests/` were written by the human's reviewer before you started. **Never edit, delete, skip, xfail or weaken them.** If a test seems wrong, stop and explain why in your reply; do not change it.
2. **Never run `git commit`, `git push`, `git reset` or `git checkout`.** The human commits. You may run `git status` and `git diff`.
3. **Stay inside the task folder** you were asked to work on. Tasks are independent; no imports between them.
4. **Do not invent requirements.** If the spec or the tests are ambiguous, list the ambiguity and the assumption you chose, and put it in the task README under "Assumptions".
5. **No secrets in code.** Configuration comes from environment variables. Never print or log tokens or keys.
6. **No `float` for money.** Use `Decimal` or integer rial. Datetimes are timezone-aware UTC.
7. **Do not add dependencies** that are not already in the task's `requirements.txt` unless the task prompt says so. Pin exact versions.
8. If the same problem fails **3 attempts in a row**, stop, summarise what you tried and what the error says, and wait for the human.
## How to work (TDD loop)
1. Read the task's tests first. They define names, signatures and behaviour.
2. Run the tests and confirm they fail for the right reason (red).
3. Write the **smallest** code that makes the next failing test pass (green). Re-run all tests after every change.
4. Refactor only while all tests are green.
5. Before reporting done, run the quality gate (below) and paste the real output. Never claim a result you did not run.
## Quality gate (run from inside the task folder, venv active)
```bash
ruff check . && ruff format --check .
pytest -q
```
Pure-logic tasks (1, 2, 9) also: `pytest -q --cov=<module> --cov-report=term-missing` (target 100% of the implementation).
 
## Code standards
- Python 3.12+, type hints on public functions, short docstring saying *what* and *why*.
- Modern typing only (ruff enforces it): built-in generics `list[int]`, `tuple[int, str]`, unions as `X | None`, and import `Iterable`/`Iterator`/etc. from `collections.abc`, never from `typing` (`List`, `Tuple`, `Optional` are forbidden).
- Small modules, one responsibility each; files over ~200 lines should be split.
- Fail loudly with specific exception classes and clear messages; no bare `except`.
- Comments explain *why*, not *what*.
- Django tasks: Django 5.x, DRF, PostgreSQL 16. Business rules live in plain functions/services, not in views. Tasks 5 and 8 need **real PostgreSQL** (never SQLite).
- Local infra: `docker compose up -d` from the repo root (Postgres 16, Redis 7). Settings read `POSTGRES_*` / `REDIS_*` env vars.
## Each task folder must end up with
Source, tests (given), a pinned `requirements.txt`, and `README.md` containing: **run command, test command, assumptions, unfinished parts** (plus the task's own deliverables from the spec, e.g. complexity analysis, diagrams, EXPLAIN ANALYZE).
 
## Reporting format when you finish a step
- What you changed (files).
- Exact commands you ran and their real output (tail is fine).
- Anything you assumed or could not do.
## Language
Reply in English. Keep answers short and concrete.
 
