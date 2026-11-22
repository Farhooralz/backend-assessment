# AGENTS.md: rules for the coding agent (OpenCode)

Hiring-test project: ten independent mini-projects (9 code, 1 design doc) for a Backend Engineer role
(Python/Django). **Autonomous mode**: the agent writes the tests, the code, the READMEs, commits and
pushes. This file overrides `docs/PLAN.md` and `docs/ENGINEERING_PLAN.md` wherever they differ
(those two assumed human-written tests and a human committer).

## Goal and scope (finish everything in ONE day)
- Requirements: `docs/TEST_SPEC.md` (the spec always wins). Per-task approach hints: `docs/PLAN.md` section 2.
- Keep it simple. **Do NOT build**: CI workflows, deployment, frontend, Swagger/OpenAPI, ADRs, DDD layers,
  extra features. Plain functions/services, small modules, the smallest design that satisfies the spec.
- Task 1 is DONE and frozen. Do not touch `task01_stream_merge/`.
- Progress lives in `docs/STATUS.md`. Update it after every task. It is how work resumes after a crash.

## Roles
- **Orchestrator** (the main session): plans, launches subagents, runs the final gate itself, updates
  `docs/STATUS.md`, and is the ONLY agent that runs `git add/commit/push`.
- **Subagent** (one per task): works only inside its own `taskNN_*/` folder. Never runs git. Never edits
  root files, `docs/`, or other tasks. Never launches more subagents.

## Non-negotiable rules
1. **Tests first, from the spec.** Every "sample / acceptance" line and every "constraints & deliverables"
   item in the task's spec section becomes at least one test, named `test_spec_<what>`. Write tests,
   run them, see them fail for the right reason, then implement.
2. **Never weaken a test to make it pass.** If a test fails, fix the code. Change a test only if it
   contradicts the spec, and say so in the README under "Assumptions".
3. **Mutation spot-check** before calling a task done: break the implementation on purpose in at least
   3 ways (e.g. flip a comparison, drop a filter, skip a lock), confirm the tests fail each time, revert.
   List the 3 mutations in the task README.
4. **Evidence over claims.** Only report results from commands you actually ran. Never invent measurements.
5. **No secrets in code.** Config from environment variables. Never print tokens, keys or `.env` values.
   Never commit `.env`, `.venv`, `*.sqlite3`, `__pycache__`.
6. **No `float` for money.** Use `Decimal` or integer rial. Datetimes are timezone-aware UTC.
7. Pin exact dependency versions in each task's `requirements.txt` (use `pip index versions <pkg>` or the
   installed version after `pip install`). Django 5.2.x, DRF, PostgreSQL 16, Celery + Redis 7 where needed.
8. **3 failures in a row** on the same problem: stop that task, write `BLOCKED` plus the reason and the last
   error in `docs/STATUS.md` (orchestrator does this), and move on to the next task.
9. Never `git push --force`, `git reset --hard`, `git rebase`, or delete branches.

## Per-task folder (each task is self-contained)
`taskNN_*/` contains: source, `tests/`, pinned `requirements.txt`, `pytest.ini` (or equivalent),
`ruff.toml`, and `README.md`.

`ruff.toml` (copy this, set the module names of the task):
```toml
extend = "../pyproject.toml"

[lint.isort]
known-first-party = ["<module names of this task>"]
```
`README.md` must contain: what it does (2-3 sentences), **run command, test command, assumptions,
unfinished parts**, the mutation list, and every deliverable the spec lists for that task
(complexity, diagrams, EXPLAIN ANALYZE, defect report, ...). Use real measured numbers only.

## Quality gate (inside the task folder, venv active)
```bash
ruff format . && ruff check . && ruff format --check .
pytest -q
```
Pure-logic tasks (2, 9) also: `pytest -q --cov=<module> --cov-report=term-missing` (aim for 100%).
Note: ruff also formats Python code blocks inside README.md, so run `ruff format .` first.

## Infrastructure (tasks 3-8)
- `cp .env.example .env` (git-ignored), then `docker compose up -d` from the repo root. Read `POSTGRES_*`
  and `REDIS_*` from the environment. If Docker is unavailable, use a local PostgreSQL/Redis through the
  same env vars; if neither exists, mark the task `BLOCKED: no postgres` and continue.
- Tasks run in parallel, so isolate them: Django `NAME` is `task03`, `task04`, ... (pytest-django creates
  `test_taskNN`), and Redis uses a different DB index per task (`redis://.../3`, `/6`, `/8`).
- Tasks 5 and 8 need real PostgreSQL. Never SQLite there.

## Code standards
- Python 3.12+, type hints on public functions, short docstrings that say *why*.
- Modern typing only: `list[int]`, `X | None`, `Iterable` etc. from `collections.abc`.
- Files over ~200 lines get split. No bare `except`. Specific exception classes, clear messages.
- Business rules in plain functions/services, not in views.
- Use `pytest-timeout` so nothing hangs.

## Git (orchestrator only)
- One commit per finished task: `git add taskNN_*/ docs/STATUS.md` (never `git add -A` or `.`), message
  `taskNN: <short summary>`. Run `git status --short` first and make sure no secrets or venvs are staged.
- `git push origin HEAD` after each wave. If push fails, report the exact error and stop pushing.

## Reporting format (subagent to orchestrator, orchestrator to human)
- Files changed, exact commands run with the tail of the real output, assumptions, unfinished parts.
- Keep it short. Reply in English.