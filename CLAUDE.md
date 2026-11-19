# Project context (read this first)

## What this is
Hiring test for a Backend Engineer role (Python/Django): ten independent mini-projects (9 code, 1 design doc), ~41 h estimated. Deadline: one week. AI assistance is explicitly allowed.

## Source of truth
- `docs/TEST_SPEC.md`: faithful English translation of the company's sheet. If anything disagrees with it, the spec wins.
- `docs/PLAN.md`: per-task plan, schedule, deployment and GitHub notes.

## Layout
One folder per task at the repo root (`task01_...` to `task10_...`), each fully independent: own `requirements.txt`, `README.md`, tests. Shared infra only: `docker-compose.yml` (Postgres 16, Redis 7). No imports between tasks.

## Technical baseline
- Python 3.12+, Django 5.x, DRF, PostgreSQL 16, Redis 7, Celery, pytest + pytest-django. Pin every version.
- Money is `Decimal` or integer rial, never `float`. Datetimes are timezone-aware UTC.
- Tasks 5 and 8 need real PostgreSQL (no SQLite).
- No secrets in code: environment variables only. `.env` is git-ignored, `.env.example` is committed.
- Setup must never need an external account. Data comes from seed scripts.
- Small modules, one responsibility each, type hints on public functions.

## Definition of Done (every task)
- Every sample/acceptance line of the spec is a passing test.
- Every "constraints & deliverables" item exists.
- README has: run command, test command, assumptions, unfinished parts.
- Works from a clean clone. I can explain every decision.

## Workflow rules (vibe-coding roadmap)
1. Plan before code: re-read the task's spec section first.
2. One small step per prompt, one task at a time.
3. Tests first (red), then minimal code (green), then refactor.
4. Review everything the AI writes. Never accept a fix I don't understand.
5. Commit after every green step.
6. Debugging: paste the error and the code, ask for the cause, add logs if stuck.
7. End of each task: a refactor pass (smaller modules, dead code, naming).
8. If the AI fails after 3 prompts: stop, open a fresh chat, paste this file.
9. Update this file whenever a decision is made or a step is finished.
10. Before finishing: security review (secrets, permissions, input validation).

## Git conventions
- `main` is always green. One branch per task: `taskNN-short-name`, merged by PR after CI passes.
- Messages: `type(scope): summary`, with type in docs, chore, test, feat, fix, refactor.
- Red then green: the failing-test commit comes before the implementation commit.

## Current status
- [x] Step 1: repo, docs, context file
- [x] Step 2: docker-compose + .env.example
- [ ] Task 1 ... Task 10: not started

## Decisions log
- T1 sample confirmed from the PDF text layer: `[(1,A,7),(3,C,4)]` + `[(1,A,7),(2,B,5)]` -> A, B, C; amount 8 for A in the second stream -> error.