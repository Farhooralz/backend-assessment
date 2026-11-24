# AGENTS.md: rules for the coding agent (OpenCode)

Hiring-test project: ten independent mini-projects (9 code, 1 design doc) for a Backend Engineer role
(Python/Django). **Autonomous mode**: the agent writes the tests, the code, the READMEs, commits and
pushes. This file overrides `docs/PLAN.md` and `docs/ENGINEERING_PLAN.md` wherever they differ
(those two assumed human-written tests and a human committer).

## Goal and scope (finish everything in ONE day)
- Requirements: `docs/TEST_SPEC.md` (the spec always wins). Per-task approach hints: `docs/PLAN.md` section 2.
- Keep it simple. **Do NOT build**: CI workflows, deployment, frontend, ADRs, DDD layers, extra features.
  Exception: Swagger/OpenAPI is REQUIRED for tasks 4 and 6 only (Round 3).
  Plain functions/services, small modules, the smallest design that satisfies the spec.
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
   installed version after `pip install`). Django 5.2.x, DRF, PostgreSQL 16, Celery + Redis where needed:
   Redis 7 when configured, but only Redis 6.2-compatible commands in the committed fallback.
8. **3 failures in a row** on the same problem: stop that task, write `BLOCKED` plus the reason and the last
   error in `docs/STATUS.md` (orchestrator does this), and move on to the next task.
9. Never `git push --force`, `git reset --hard`, `git rebase`, or delete branches.

## Round-2 rules (added after external review; these override anything above that conflicts)

10. **Red first, with proof.** For every fix, first write a test that fails on the CURRENT code for the
    stated reason. Run it, and paste the failing assertion line into the task README under "Round 2".
    If a listed finding does NOT reproduce, do not force a fix. Write "not reproduced" and the evidence.
11. **Mutation checks must hit business logic.** A mutation is valid only if it changes behaviour
    (drop a filter, flip `<` to `<=`, remove `atomic()`, skip a lock, drop `distinct`). Mutating
    `ensure_db`, a benchmark selector, a README, or a type hint does not count. Every README mutation table
    names the exact test that fails (`file::test_name`).
12. **No grep-as-proof.** Tests that grep the README or the source (e.g. "README mentions lock order",
    "source has no `threading.Lock`") may exist only as extra deliverable-presence checks. Each such
    deliverable also needs a behavioural test. Delete tests that are tautological or duplicate another test.
13. **Every number in a README must be reproducible.** If a README says "252 queries", "36 cases" or
    "9.45s", a test or a command in the repo must print/assert exactly that. Test counts come from
    `pytest --collect-only -q | tail -1`. Remove any claim you cannot reproduce.
14. **Atomicity/rollback tests** use `@pytest.mark.django_db(transaction=True)`, inject the failure AFTER
    the first write has happened, and then verify state through a SEPARATE connection. A failure injected
    before any write proves nothing.
15. **Concurrency tests:** open the DB connection first, then wait on the barrier. Keep every connection
    open until after all workers finish if the test asserts distinct `pg_backend_pid()`s. Use real
    processes (`multiprocessing`, spawn) where the spec says "workers"; threads are acceptable only for DB
    row-lock races.
16. **Honest docs.** If behaviour differs from what a README/docstring says, fix the text or the code in the
    same commit. Wrong docs count as a bug. Spec ambiguities go under "Assumptions" with a ⚠ marker.

Commits: one commit per task per round: `taskNN: round 2 - <summary>`. Same git rules as before.
Subagents may run in parallel (tasks are independent), but the orchestrator must run every gate itself
before committing.

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
Get PostgreSQL + Redis running with this order, stop at the first one that works:
1. Docker: `cp -n .env.example .env && docker compose up -d`. If it prints "permission denied" (or any
   docker error), do NOT mark anything BLOCKED, go to step 2.
2. No-Docker fallback (no root needed): `scripts/local_infra.sh start`. It installs real PostgreSQL 16 and
   Redis into a git-ignored venv, starts them, and writes `.env`. Check with `scripts/local_infra.sh status`.
3. Only if both fail, mark the tasks `BLOCKED: no postgres` with the exact error in `docs/STATUS.md`.

Env contract (the same for both options). Task settings read these with `os.environ`:
`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_HOST`, `REDIS_PORT`.
With the fallback, `POSTGRES_HOST` is a unix-socket directory and `POSTGRES_PORT` / `POSTGRES_PASSWORD` are
empty. Pass them to Django as they are (empty string is fine). Defaults when unset: host `localhost`,
port `5432`, user `assessment`, Redis `127.0.0.1:6379`. In every README, the test command loads the file:
`set -a; . ../.env; set +a; pytest -q`.

Isolation, because tasks run in parallel: Django `NAME` is `task03`, `task04`, ... and must be created
before tests (`createdb`-style via `psycopg` in a `conftest.py` fixture or a management command);
pytest-django then creates `test_taskNN`. Redis uses a different DB index per task (`/3`, `/6`, `/8`).
Tasks 5 and 8 need real PostgreSQL. Never SQLite there. The fallback Redis is 6.2; use only commands that
exist in 6.2.

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