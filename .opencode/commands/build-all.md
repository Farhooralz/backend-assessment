---
description: Build tasks 2-10 end to end with parallel subagents, then commit and push
agent: build
---

You are the ORCHESTRATOR. Read `AGENTS.md` fully and obey it. Goal: finish tasks 2 to 10 today, in waves,
using parallel subagents, with the smallest design that satisfies `docs/TEST_SPEC.md`.

Optional argument: `$ARGUMENTS`. If it is a wave number (1, 2, 3 or 4), run only that wave. If empty, run
all waves in order and resume from `docs/STATUS.md`: skip every task already `DONE`.

Current status and git state:
!`cat docs/STATUS.md`
!`git status --short`
!`git branch --show-current`

## Wave plan

| Wave | Tasks (run in parallel) | Needs |
|------|-------------------------|-------|
| 1 | T2 pricing engine, T9 cancellation tests, T10 ERP architecture doc | nothing |
| 2 | T3 court report, T7 debtors refactor, T4 goods transfer API, T6 JWT + branch access | PostgreSQL (T6 also Redis) |
| 3 | T5 last-seat reservation, T8 receipt outbox | PostgreSQL + Redis, real concurrency |
| 4 | Finalize (you alone, no subagents) | everything |

Folder names: `task02_pricing_engine`, `task03_court_report`, `task04_goods_transfer_api`,
`task05_last_seat_reservation`, `task06_jwt_branch_access`, `task07_debtors_refactor`,
`task08_receipt_outbox`, `task09_cancellation_tests`, `task10_erp_architecture`.

## How to run a wave

1. Before wave 2: bring up PostgreSQL + Redis exactly as the "Infrastructure" section of `AGENTS.md` says
   (Docker first; if Docker fails for any reason, run `scripts/local_infra.sh start`). Verify with a real
   connection test (psql/psycopg and `redis ping`), and do not print `.env` values. Docker permission errors
   are NOT a reason to block tasks.
2. Set the tasks of the wave to `IN_PROGRESS` in `docs/STATUS.md`.
3. Launch ALL subagents of the wave in ONE message (several Task tool calls at once, subagent type
   `general`) so they truly run in parallel. Give each subagent the brief below, filled in.
4. When they report back, YOU re-run each task's quality gate yourself (do not trust the report):
   `cd taskNN_* && ruff format . && ruff check . && ruff format --check . && pytest -q`.
   If a gate fails, send that one task back to a fresh subagent with the exact error (max 2 retries,
   then `BLOCKED`).
5. For each task that passes: update `docs/STATUS.md` to `DONE` with one line of notes, then
   `git add taskNN_*/ docs/STATUS.md`, commit `taskNN: <summary>`. After the wave: `git push origin HEAD`.
6. Continue to the next wave without asking me. Stop only on a push failure or when everything is done.

## Subagent brief (copy, fill in the task, send)

> You are the implementer for TASK <NN> in `<taskNN_folder>/`. Read `AGENTS.md`, then ONLY the Task <NN>
> section of `docs/TEST_SPEC.md` and the Task <NN> part of `docs/PLAN.md` section 2. Work only inside
> your folder. Do not run git. Do not launch subagents. Follow the TDD loop in `AGENTS.md`:
> 1. Create the folder skeleton (`requirements.txt` pinned, `pytest.ini`, `ruff.toml`, `tests/`).
> 2. Write the tests FIRST: one `test_spec_*` test per sample/acceptance line and per spec constraint,
>    plus the edge cases from the PLAN.md hints. Run them and confirm they fail for the right reason.
> 3. Implement the smallest code that turns them green. No extras.
> 4. Mutation spot-check (3 deliberate breaks, revert each) and list them in the README.
> 5. Write `README.md` (run, test, assumptions, unfinished, plus every deliverable the spec lists) with
>    real measured numbers only.
> 6. Run the quality gate and reply with: files changed, exact commands with real output tails,
>    assumptions, anything unfinished. Be short.

Task-specific notes to add to the brief:

- **T2**: stdlib + pytest only. `Decimal` everywhere, `ROUND_HALF_UP` only at the end. A shared contract
  test run against every policy. Class diagram in Mermaid inside the README, plus a short explanation of
  Polymorphism, Encapsulation, Abstraction, Composition. The 4th policy is yours, documented.
- **T9**: pytest + pytest-django, minimal `cancel` service with an injectable clock (no wall clock inside
  the logic). Boundary tests at exactly 24h (101), +1s (50), exactly 2h (50), +1s (0), at start (rejected).
  Permission, unit, integration and failure tests (document write fails, cancellation rolls back). Add
  `mutation_check.py` that applies 3 deliberate defects to a temp copy of the implementation (`>` vs `>=` at
  24h, rounding up instead of down, cancel committed before the refund document), runs pytest on each,
  and prints which test names fail. Put that table in the README. SQLite is allowed for this task only.
- **T10**: documentation only, in `task10_erp_architecture/README.md` (or `DESIGN.md` linked from it). Must
  contain every section listed in the spec and PLAN.md (assumptions, API boundary, Mermaid ERD, Mermaid
  sequence diagram for the late-payment sample with reservation status, money, user message and
  reconciliation at each step, capacity model, SLO with p95 = 250 ms, indicators and alerts, recovery plan,
  load-test plan, two decisions with their cost or limitation). Add `check_doc.py` that fails if a required
  section or diagram is missing, and run it.
- **T3**: models, migration, `CheckConstraint(amount > 0)`, naive version and optimized version (per-table
  aggregates so payments x tags never multiply sums), `assertNumQueries`/`CaptureQueriesContext` test with
  at most 5 queries for a page of 50 courts, equivalence test naive == optimized, seed command for
  100,000 bookings, suggested indexes, and a real `EXPLAIN ANALYZE` before/after pasted in the README.
- **T7**: write the regression (characterization) tests first, then one failing test per defect, then the
  rewrite. At most 3 queries for 100 invoices. Defect report in the README, in priority order.
- **T4**: DRF ViewSet, state machine draft -> submitted -> approved or rejected, `status` read-only, 404 for
  records outside visibility, 403 for forbidden actions, 409 on a second decision, 400 on quantity <= 0
  or source == destination, decision-maker taken from `request.user`, stable ordering, status filter,
  pagination, role-matrix test (role x action x expected code).
- **T6**: PyJWT or SimpleJWT (pick one, say why). Sessions table, access 5 min, refresh 7 days, rotation,
  logout closes the session, live membership check on every request, `get_queryset` always scoped (fixes
  the IDOR), 6th failed login in 60 s gives 429 with the counter in Redis (shared across workers), expired
  token gives 401 using a controlled clock, no tokens in logs (test it). Include the IDOR note.
- **T5**: `select_for_update` on the class row first, idempotency key, unique constraints, `TransactionTestCase`
  on real PostgreSQL, 20 threads each with its own connection released together by a `threading.Barrier`
  (exactly 3 successes and 17 conflicts), same-key-same-user race returns one shared id, rollback test
  (failure mid-operation leaves capacity unchanged), lock-order explanation in the README. Run the
  concurrency tests 5 times in a row to prove they are not flaky.
- **T8**: transactional outbox (payment and outbox row in one transaction), `on_commit` plus a periodic
  sweeper, `select_for_update(skip_locked=True)` claiming, idempotency key, up to 5 attempts with increasing
  intervals, permanent error stops immediately, operator retry (management command), Fake service with
  modes `ok`, `temporary_error`, `permanent_error`, `accept_then_timeout`. Tests: rollback creates no
  message, timeout-after-accept gives exactly one external message and one local receipt, two workers one
  payment, crash between "sent" and "recorded". Celery can run eagerly in tests; Redis is the real broker
  in settings. README: Fake-worker contract, recovery path, how to observe failed attempts.

## Wave 4: finalize (you alone)

1. Update the root `README.md` table: status of each task, and one run command and one test command per task.
2. Verify from a clean clone: `git clone . /tmp/clean-check`, then for every `DONE` task create a fresh venv
   in its folder, install its `requirements.txt` and run its gate. Report the real results in a table.
   Do not commit `/tmp` or any venv.
3. Add to the root README an honest note: AI assistance was used; tests were generated from the spec first
   and mutation-checked; every task README lists its assumptions.
4. Update `docs/STATUS.md`, commit `docs: final status`, `git push origin HEAD`.
5. Final report to me: a table of all 10 tasks with status, test counts, and anything BLOCKED with the
   reason. Keep it under 40 lines.