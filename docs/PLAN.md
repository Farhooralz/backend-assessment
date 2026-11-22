
# Project Plan & Tracker
 
Source of truth for requirements: **`TEST_SPEC.md`**. If this plan and the spec disagree, the spec wins.

## Round 2 (authoritative note)

Round 2 followed [`docs/ROUND2_BRIEF.md`](ROUND2_BRIEF.md). `AGENTS.md` and `TEST_SPEC.md` win wherever the older plan text below still mentions CI, deployment, frontend, Swagger, ADRs or reviewer-written tests. Those items were deliberately not built. Live status is in [`STATUS.md`](STATUS.md); the rest of this file is kept as the original design history.
 
## 0. Working rules
 
1. **Spec first.** Before each task: re-read its section in `TEST_SPEC.md`, then turn every sample and acceptance line into a **failing test** before writing the implementation.
2. **Independence.** Each task is a self-contained folder: own `requirements.txt` (pinned), own `README.md`, own tests. No imports between tasks.
3. **Definition of Done (per task)**
   - [ ] Every sample/acceptance line from the spec is a passing test
   - [ ] Every "constraints & deliverables" item is present
   - [ ] README has: **run command, test command, assumptions, unfinished parts**
   - [ ] Versions pinned; works on Python 3.12+ (Django 5.x, DRF, PostgreSQL where relevant)
   - [ ] Data is seed-built; no external account required
   - [ ] Runs from a **clean clone** (verified)
   - [ ] I can explain every decision out loud (interview follow-up)
4. **Never** change behavior to make a test pass without checking the spec.
5. Commit per task with a message like `task05: reserve with select_for_update + idempotency`.
## 1. Repository layout
 
```
backend-assessment/
├── README.md                  # index: tasks and how to run each
├── TEST_SPEC.md               # source of truth (translated PDF)
├── PLAN.md                    # this file (original design history)
├── docker-compose.yml         # postgres + redis (shared by tasks that need them)
├── task01_stream_merge/       # stdlib only
├── task02_pricing_engine/
├── task03_court_report/
├── task04_goods_transfer_api/
├── task05_last_seat_reservation/
├── task06_jwt_branch_access/
├── task07_debtors_refactor/
├── task08_receipt_outbox/
├── task09_cancellation_tests/
└── task10_erp_architecture/   # docs only (Markdown + Mermaid diagrams)
```
 
Every task folder: `README.md`, `requirements.txt`, source, `tests/`, and (where needed) `docker-compose.yml` or a pointer to the root one.
 
## 2. Task-by-task plan
 
Order is chosen to build momentum and keep the hardest, most-probed tasks for when the environment is stable.
 
| Day | Tasks | Why this order |
|-----|-------|----------------|
| 0 | Skeleton, Docker (Postgres + Redis), CI, README template | Everything later depends on it |
| 1 | **T1, T2, T9** | Mostly pure logic, fast wins, build the testing habit |
| 2 | **T3, T7** | ORM and query counting, shared seed approach |
| 3 | **T4, T6** | DRF permissions and auth |
| 4 | **T5, T8** | Concurrency and failure recovery (hardest) |
| 5 | **T10**, then clean-clone verification of all tasks | Design doc, final polish |
| 6 | Buffer: re-read all code, rehearse explanations | Interview follow-up |
 
### T1: Stream merge (stdlib only)
- Approach: `heapq` holding at most one pending item per stream (`(time, id, stream_index, amount)`); on pop, **drain every head with the same `(time,id)`**, compare amounts, raise a dedicated exception before yielding; then advance those streams.
- Tests first: the A/B/C sample; amount-8 conflict; empty input; all-empty streams; equal times with different ids; 64 streams; `itertools.count` infinite iterator consumed with `islice`; `tracemalloc` memory check that stays flat as data grows.
- Deliver: complexity analysis (O(N log k) time, O(k) space) and the memory measurement in the README.
### T2: Pricing engine
- Approach: `Policy` abstract base class with `apply(Money-in-Decimal, context) -> Result`; `QuoteEngine` composes an ordered list of policies; breakdown records each step's before/after. All `Decimal`, `quantize(ROUND_HALF_UP)` only at the end; clamp at 0.
- Policies: `HourMultiplier`, `PercentDiscount` (membership), `FixedCredit`, plus my 4th (e.g. `PeakSurcharge` or `LoyaltyCap`, documented).
- Tests first: 1000 → 1150; credit 2000 → 0; idempotent re-run; reject float input; a shared **contract test** run against every policy; adding a policy without editing the engine.
- Deliver: class diagram (Mermaid), and the 4-concept explanation (Polymorphism, Encapsulation, Abstraction, Composition).
### T3: Court report
- Models: Branch, Court (FK Branch), Tag, Booking (FK Court, M2M Tag), Payment (FK Booking, `amount > 0` CheckConstraint).
- Naive version (N+1 measured) vs optimized: aggregate **per-table subqueries or `Count(distinct=True)`/`Sum` with filter** so payments × tags does not multiply sums. Tags via a separate prefetch or `ArrayAgg(distinct=True)`. Date filter applied inside the aggregates so empty courts still appear.
- Tests first: the 200 / count 1 / 3 tags sample; empty court = 0; page of 50 courts ≤ 5 queries (`assertNumQueries`/`CaptureQueriesContext`).
- Deliver: 100k-booking seed command, suggested indexes, `EXPLAIN ANALYZE` before vs after in the README.
### T4: Goods transfer API (DRF)
- State machine: `draft → submitted → approved | rejected`. Actions: `submit`, `approve`, `reject` (reason required) as ViewSet actions. `status` is read-only in the serializer.
- Visibility via `get_queryset` (404 outside scope); permission classes for action rights (403); 409 on second decision; 400 on quantity ≤ 0 or source == destination; decision-maker taken from `request.user`.
- Tests first: the sample cycle, plus a **role-matrix test** (role × action × expected code). Stable pagination (`ordering = ("-created_at","-id")`), filters on status.
### T5: Last-seat reservation (real concurrency)
- Approach: in one transaction: `select_for_update` the class row → check idempotency key → check user's existing reservation → check capacity → insert. Constraints: `UniqueConstraint(user, class)`, `UniqueConstraint(user, key)`.
- Idempotency race: two threads, same key and user → one inserts, the other gets the same id (handle `IntegrityError` by re-reading).
- Tests first: 20 threads with independent connections and a `threading.Barrier` → exactly 3 × 201 / 17 × 409; same-key same-user shared id; rollback test (inject failure mid-transaction → capacity unchanged). Use `TransactionTestCase` against real PostgreSQL (no SQLite).
- Deliver: Lock-order explanation (always lock class row first, then user-scoped rows, never the reverse).
### T6: JWT and branch access
- Library: PyJWT (or SimpleJWT, decided at task start). Sessions table: `session_id`, `refresh_jti`, `revoked_at`. Access 5 min, refresh 7 days, rotation on every refresh; reuse of an old refresh kills the session. Logout revokes the session; the access token carries `sid` and each request checks it is live.
- Fix IDOR: `get_queryset` always returns `visible_invoices(user)` for **every** action (list and detail), so out-of-scope → 404. Membership checked live from the DB each request.
- Rate limit: per-account, 60 s window, 6th failed attempt → 429, store shared across workers (Redis `INCR`+`EXPIRE`, or DB cache). Never log tokens or keys.
- Tests first: membership removal; expired token 401; two sessions are independent; 6th failure 429; IDOR attempt on detail.
- Deliver: IDOR note.
### T7: Debtors refactor
- Defects to report (priority order): (1) no status filter (draft/settled/cancelled leak); (2) no membership/branch authorization; (3) pending payments counted as paid; (4) negative dues returned (`!=` vs `>`); (5) N+1 queries; (6) no ordering.
- Step 1: **characterization tests** that pin current correct behavior (signature, output keys/shape). Step 2: failing tests for each defect. Step 3: rewrite with one annotated query (`Sum("payments__amount", filter=Q(payments__status="settled"))`, `Coalesce`) + one membership query ≤ 3 total for 100 invoices.
### T8: Receipt dispatch (transactional outbox)
- Approach: payment and `OutboxMessage` inserted in the **same transaction**; `transaction.on_commit` triggers Celery, but a **periodic sweeper** picks up pending outbox rows so a Broker crash after commit loses nothing. Row-claim with `select_for_update(skip_locked=True)` (two workers safe). Idempotency key sent to the external service. Retry up to 5 with exponential backoff; permanent errors → `failed` immediately; operator retry via admin action / management command.
- Fake external service modes: `ok`, `temporary_error`, `permanent_error`, `accept_then_timeout`.
- Tests first: rollback → no outbox row; timeout-after-accept → exactly one external message and one local receipt after recovery; two workers one payment; crash between "sent" and "recorded"; backoff schedule; operator retry.
- Deliver: Fake-worker contract, recovery path, guide for observing failed attempts.
### T9: Cancellation policy tests
- Minimal implementation, then a test suite that **controls the clock** (injected `now` or `freezegun`). Boundary tests: exactly 24h (101), 24h + 1s later (50), exactly 2h (50), 2h + 1s later (0), at start → rejected. Atomicity failure test (document write fails → cancellation rolled back). Repeat returns previous result. Permission tests (owner, same-branch manager, others).
- Deliver: **three deliberate defects** (e.g. `>` vs `>=` at 24h, rounding up instead of down, cancel committed before refund document) each mapped to the exact test name that catches it.
### T10: ERP architecture (docs only)
- Sections: assumptions, API boundary, ERD (Mermaid), sequence diagram for the late-payment sample, capacity model (300 rps reserve, 3000 rps availability, hot court ≈150 rps), SLOs (p95 availability ≤ 250 ms), indicators and alerts, recovery plan, load-test plan, two decisions with cost/limitation.
- Key ideas to cover: PostgreSQL **exclusion constraint** on `tstzrange` per court for overlap prevention; 10-minute `held` state with expiry sweeper; idempotent payment callbacks (provider reference unique); availability cache (Redis, short TTL, invalidate on change); report via read replica or materialized aggregates (5-min staleness); late payment after expiry → automatic refund + user message + reconciliation entry; per-court serialization for the hot court.
## 3. Progress tracker
 
Update as we go (`[ ]` → `[x]`).
 
| # | Task | Spec re-read | Tests written | Implemented | README done | Clean-clone verified | I can explain it |
|---|------|:-:|:-:|:-:|:-:|:-:|:-:|
| 0 | Skeleton + local infra fallback | [x] | n/a | [x] | [x] | [x] (fallback script verified from a clean clone in Round 1; Docker/CI intentionally not built) | [ ] |
| 1 | Stream merge | [x] | [x] | [x] | [x] | [x] | [ ] (your job: read `stream_merge.py` + README) |
| 2 | Pricing engine | [x] | [x] | [x] | [x] | [x] | [ ] |
| 3 | Court report | [x] | [x] | [x] | [x] | [x] | [ ] |
| 4 | Goods transfer API | [x] | [x] | [x] | [x] | [x] | [ ] |
| 5 | Last-seat reservation | [x] | [x] | [x] | [x] | [x] | [ ] |
| 6 | JWT + branch access | [x] | [x] | [x] | [x] | [x] | [ ] |
| 7 | Debtors refactor | [x] | [x] | [x] | [x] | [x] | [ ] |
| 8 | Receipt outbox | [x] | [x] | [x] | [x] | [x] | [ ] |
| 9 | Cancellation tests | [x] | [x] | [x] | [x] | [x] | [ ] |
| 10 | ERP architecture doc | [x] | n/a | n/a | [x] | [x] | [ ] |

Note (2026-11-22): AGENTS.md autonomous mode overrides the human-writer/human-committer assumption above. Tasks 2-10 were implemented and clean-clone verified in Round 1; Round 2 followed `docs/ROUND2_BRIEF.md` and is tracked in `docs/STATUS.md`. No CI workflow, deployment or frontend was added. The last column (human explanation) is intentionally left unchecked.
 
## 4. Repository history

The repository already exists. The orchestrator commits one task at a time and pushes to `dev`. No CI workflow was added because `AGENTS.md` forbids it. `.gitignore` ignores `.env`, `.venv`, `*.sqlite3` and `__pycache__`; `.env.example` is committed.

## 5. Deployment (not built)

Not built. `AGENTS.md` forbids deployment work and the spec requires local setup with no external account.

## 6. Frontend (not built)

Not built. No UI, Swagger page, static host or demo page; all deliverables are local backend code, tests and documentation.
## 7. Open items to confirm
 
- Is AI assistance allowed for this test? (Ask the company; either way, we build so you can explain everything.)
- Deadline?
- Private repo OK, or must it be public?
- Preferred JWT library for T6 (PyJWT vs SimpleJWT)? Default: decide at task start.
 
