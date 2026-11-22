# Engineering Plan (addendum to PLAN.md)
 
Requirements live in `docs/TEST_SPEC.md` (source of truth). `docs/PLAN.md` has the original task plan, deployment and GitHub notes. This file adds everything needed to build the project the way a strong engineering team would, with OpenCode (model: Big Pickle) writing the implementation and the tests acting as the contract.
 
## 1. Principles
 
"Enterprise quality" here means: correct, verifiable, readable, and honest about trade-offs. It does **not** mean maximum ceremony; reviewers of a time-boxed test reward correctness, edge cases, concurrency safety, query counts and a clear README far more than layers of abstraction.
 
1. **Spec-driven**: every sentence of the spec's "sample/acceptance" becomes an automated test.
2. **Tests as the contract**: tests are written *before* and *independently of* the implementation (by the reviewer, not by the coding agent), then frozen.
3. **Small steps, always green**: red, green, refactor; one commit per green step.
4. **Evidence over claims**: every "done" is backed by pasted command output.
5. **Decisions are written down**: assumptions go in task READMEs; architecture choices go in `docs/adr/`.
6. **Human in the loop**: the human reads and can explain every line; the agent never commits.
## 2. Test strategy: options and decision
 
| Option | What it is | Strengths | Weaknesses | Fit |
|---|---|---|---|---|
| A. Pure TDD (pytest) | Unit tests drive each function/class | Fast, simple, minimal tooling | Acceptance intent is implicit | Good inner loop |
| B. BDD with Gherkin (`pytest-bdd`, `.feature` files) | Scenarios in Given/When/Then text bound to step functions | Reads like the spec, great for non-developers | Extra dependency, step-glue boilerplate, duplication, harder for a free model to get right | Overkill here |
| **C. Hybrid (chosen)** | **Acceptance tests in Given/When/Then style written as plain pytest**, TDD at unit level, **property-based tests** (Hypothesis) for algorithmic tasks, **resource/concurrency tests** where the spec demands them, **mutation checks** as a final gate | Same readability as BDD without the glue; catches edge cases humans miss; proves tests have teeth | Slightly more test code | Best value |
| D. Full DDD + hexagonal for every task | Domain / application / infrastructure layers, repositories, ports and adapters | Scales to large systems | 3-5 hour tasks drown in ceremony; reviewers may read it as over-engineering | Only selectively |
 
**Decision (ADR-0001): Option C.**
- **DDD-lite, applied selectively**: value objects and strategy-style policies in Task 2; a domain service plus a thin persistence boundary in Tasks 5, 8, 9; bounded contexts in the Task 10 document. Django-idiomatic "services and selectors" in the DRF tasks. No ceremony where it does not pay.
- **TDD** inside each task: smallest passing step.
- **BDD-style naming**: `test_given_..._when_..._then_...` with Given/When/Then comments, so a reviewer can read tests as the spec.
- If you prefer real Gherkin later, only the acceptance layer changes; unit, property and resource tests stay.
## 3. Test layers per task (the reviewer writes these before OpenCode implements)
 
| # | Task | Layers |
|---|---|---|
| 1 | Stream merge | Acceptance (spec lines), property tests vs a reference model, resource tests (memory, read-ahead), tripwire infinite streams, stdlib-only check, mutation checks |
| 2 | Pricing engine | Acceptance (1000 gives 1150, credit 2000 gives 0, repeatability), shared **contract test** run against every policy, property tests (never negative, deterministic, Decimal only), extensibility test (external policy without editing the engine), no-float static check |
| 3 | Court report | DB acceptance (200 / count 1 / 3 tags, empty court), model constraint tests, **query-count tests** (naive vs optimized), equivalence test naive == optimized on random data, seed-command test; EXPLAIN ANALYZE captured in README |
| 4 | Goods transfer API | API acceptance with `APIClient`, **role-matrix** (role x action x expected status), state-machine unit tests, status-not-writable test, stable-pagination test |
| 5 | Last seat | Real-PostgreSQL concurrency tests (threads, independent connections, `Barrier`), idempotency race, rollback-injection test, constraint tests |
| 6 | JWT + branch access | Auth flow acceptance, **IDOR tests**, expiry via controlled clock, 6th failure gives 429 and the limiter is shared across processes, no-token-in-logs test |
| 7 | Debtors refactor | Characterization tests of today's correct behaviour, one failing test per defect, query-count test (at most 3 for 100 invoices), equivalence vs a pure-Python reference |
| 8 | Receipt outbox | Atomicity (rollback gives no message), Fake service modes (ok, temporary, permanent, accept-then-timeout), crash-at-boundary tests, two workers with `SKIP LOCKED`, backoff schedule unit tests, operator retry |
| 9 | Cancellation tests | Here **tests are the deliverable**: the reviewer provides a **mutation harness** that injects the 3 deliberate defects and checks the candidate's suite fails for each; boundary-value tests at exactly 24 h, 2 h and one second either side |
| 10 | ERP architecture | "Documentation tests": a script that checks every required section and diagram exists (API boundary, ERD, sequence diagram, capacity model, SLO, alerts, recovery plan, load test, assumptions, two cost/limitation decisions) |
 
## 4. Quality gates (Definition of Done, per task)
 
Run from inside the task folder with the venv active:
 
```bash
ruff check . && ruff format --check .
pytest -q                                   # includes timeouts (pytest-timeout)
pytest -q --cov=<module> --cov-report=term-missing   # pure-logic tasks: aim for 100%
```
 
Plus, per task:
- [ ] Every sample/acceptance line of the spec is covered by a test
- [ ] README with run command, test command, assumptions, unfinished parts and the task's own deliverables
- [ ] Mutation check: break the implementation on purpose in several ways; the tests must fail each time (record the list in the README)
- [ ] Clean-clone run in a fresh virtualenv
- [ ] The human can explain every decision (use the `/explain` command to rehearse)
Project-level gates (before submitting):
- [ ] CI green on GitHub Actions (lint + tests per task; Postgres/Redis service containers for tasks 3-8)
- [ ] Secrets review: no secrets in code or history, `.env` ignored, `.env.example` committed
- [ ] Security review pass: authorization on every endpoint, input validation, no sensitive data in logs
- [ ] Root README lists all tasks, run/test commands, and an honest note that AI assistance (allowed by the company) was used, with tests written first and implementations reviewed
Tooling notes: `ruff` (lint, format) is configured once in the root `pyproject.toml`. `pytest-timeout` is in every task so a runaway implementation cannot hang your machine. Tests that read "infinite" streams use a **tripwire** that raises after a bounded number of reads so a non-lazy implementation fails fast instead of eating memory. Optional extras if time allows: `mutmut` for automated mutation testing, `pip-audit` for dependency vulnerabilities, `gitleaks` for secret scanning. These are optional and not yet verified in this project.
 
## 5. Per-task approach (design intent, details in PLAN.md)
 
- **T1** single module, heap-based k-way merge, O(k) memory.
- **T2** `Policy` abstract base, ordered composition in a `QuoteEngine`, `Decimal` end to end, breakdown as data.
- **T3** per-table aggregates (avoid join fan-out), filters inside the aggregates, tags fetched without multiplying rows.
- **T4** DRF ViewSet with explicit transition actions, visibility via `get_queryset`, permissions for action rights.
- **T5** `select_for_update` on the class row, unique constraints for idempotency, consistent lock order.
- **T6** library JWT, server-side sessions table, rotation on refresh, live membership check, shared rate limiter.
- **T7** one annotated query plus one membership query, characterization tests first.
- **T8** transactional outbox, `SKIP LOCKED` claiming, idempotency key, exponential backoff capped at 5 attempts.
- **T9** minimal cancel service, injectable clock, atomic cancel plus refund record.
- **T10** Markdown with Mermaid diagrams; exclusion constraint on `tstzrange`, 10-minute holds, idempotent callbacks, cached availability, late-payment refund path.
## 6. Repository additions
 
```
backend-assessment/
├── AGENTS.md                   # rules OpenCode reads automatically (replaces CLAUDE.md)
├── opencode.json               # pins the model
├── pyproject.toml              # ruff configuration (shared)
├── requirements-dev.txt        # ruff (shared tooling)
├── .opencode/commands/         # /implement /verify /review /refactor /readme /explain
├── docs/
│   ├── TEST_SPEC.md  PLAN.md  ENGINEERING_PLAN.md
│   └── adr/                    # architecture decision records (ADR-0001 = section 2)
└── taskNN_*/ ...               # each task: src, tests/, requirements.txt, README.md
```
 
ADR template (copy for each decision): title, status, context, decision, consequences.
 
## 7. OpenCode workflow per task
 
1. **Reviewer (Claude)** delivers the task's tests (verified against a private reference implementation and deliberately broken variants) and the OpenCode prompt.
2. **You** create the branch `taskNN-name`, add the tests, install deps, run them to see red, commit `test(taskNN): add contract tests`.
3. **OpenCode** `/implement`: smallest code to green; never touches tests; pastes real output.
4. **You** run the quality gate yourself (do not trust the agent's report), then read the diff.
5. `/review` (read-only agent): checks the diff against the spec and confirms the tests were not modified.
6. `/refactor`, `/readme`, `/explain`: tidy, document, rehearse.
7. **You** commit, push, open a PR, wait for CI, merge. Tick the tracker.
Rules of thumb for a free model: one small prompt at a time; if it fails 3 times, start a fresh session and re-run the bootstrap prompt; keep sessions short so context stays clean.
 
## 8. Risk register
 
| Risk | Impact | Mitigation |
|---|---|---|
| Free model (Big Pickle) is weaker or unavailable (free Zen models have had outages) | Delays, wrong code | Tests-as-contract catch wrong code; switch model in `/models` (other free Zen models exist); implement the hardest tasks (5, 8) in small steps or hand the reasoning to Claude here |
| Agent edits tests to pass | False green | AGENTS.md rule, `/review` diff check on `tests/`, human runs the gate |
| Agent hallucinates Django/DRF/Celery APIs | Broken code | Pinned versions, tests run for real, short feedback loops |
| Concurrency tests flaky (T5, T8) | Lost time | Barriers, independent connections, bounded timeouts, run several times |
| Docker unavailable on some machine | Cannot run T3-T8 | Documented fallback to a local PostgreSQL via env vars |
| Spec ambiguity | Wrong interpretation | Decisions log in `AGENTS.md`/READMEs, listed assumptions |
| Over-engineering | Missed deadline | DDD-lite only where it pays; Definition of Done is the stop signal |
| Not being able to explain the code in the follow-up interview | Fails the interview | `/explain`, daily read-through day, you review every diff |
 
## 9. Schedule (deadline: one week; target: 5 working days + buffer)
 
| Day | Work |
|---|---|
| 0 | Repo bootstrap, OpenCode setup, CI skeleton, Task 1 end to end (proves the loop) |
| 1 | T2, T9 |
| 2 | T3, T7 |
| 3 | T4, T6 |
| 4 | T5, T8 |
| 5 | T10, project-level gates, clean-clone run of everything |
| 6 | Buffer, rehearse explanations, final README polish |
 
## 10. Status board
 
| # | Tests delivered | Red committed | Implemented | Gate passed | README | Reviewed (`/review`) | Explained |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 | [x] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| 2-10 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
 
