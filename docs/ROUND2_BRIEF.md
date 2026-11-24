# ROUND 2: FIX BRIEF (read AGENTS.md "Round-2 rules" first)

Context: an external review found real defects and several weak tests. The reviewer could not run the
Django tasks, so REPRODUCE EACH BUG RED FIRST (rule 10). Task 1 is frozen: no changes. Order of work: P0
items first, then P1, then P2. For each task, finish with the full gate, a fresh mutation table
(rule 11), a README "Round 2" section, and a STATUS.md update.

## task08_receipt_outbox  (P0, has a real bug)

1. **BUG: backoff bypass.** In `process_outbox_message`, after locking the row:
   `if status == PENDING and next_attempt_at > moment: return PENDING` (no attempt consumed, no send).
   Tests: (a) PENDING row with future `next_attempt_at` processed early -> `attempts` unchanged, fake
   service call count 0; (b) the sweeper enqueues the same due row twice back to back -> exactly 1 send
   and 1 attempt; (c) after a temporary failure, a duplicate task run immediately does not send.
2. **Stale worker must not overwrite state.** Before `_defer`, `_fail` and the SENT write: re-lock the row
   (`select_for_update`) and verify `status == IN_PROGRESS` and `attempts == attempts_at_claim`; otherwise
   return the current status without writing. Do `record_receipt` and the SENT update in ONE
   `transaction.atomic()` (record_receipt must stay idempotent). Test: worker A claims; the lease
   expires; worker B finishes -> SENT; A's late `_defer` must leave SENT.
3. **Crash loop cap.** Re-claiming a stale IN_PROGRESS row now counts as an attempt. If that would
   exceed MAX_ATTEMPTS -> FAILED with `last_error="worker crashed repeatedly"`. Update the existing
   "crash recovery is not a new attempt" test deliberately and say so in the README Assumptions.
4. **Sweeper docs are wrong.** The `skip_locked` lock is released before enqueue, so claims are not
   exclusive. Do not redesign. Fix the README and docstring to say: duplicates are possible and harmless
   because of (1) the row lock, (2) the lease/backoff checks, (3) the idempotency key. Rename
   `test_spec_select_for_update_skip_locked_claiming` to say what it proves.
5. **Operator retry command** must use the same safe enqueue helper as the sweeper (broker down => the row
   stays PENDING and the sweeper recovers it; no exception after the state change). Test it with the
   publish patched to raise `redis.exceptions.ConnectionError`.
6. **Spec sample test must be real.** Add a fake mode `accept_then_timeout`: it records the message,
   then raises the timeout. Do NOT patch `lookup`. Assert exactly 1 external message and 1 local receipt
   after recovery. Add a second variant where lookup finds nothing, so the retry resends -> still 1
   external message.
7. **One clock.** Sweep and task must use the same injected/frozen `now` (e.g. monkeypatch
   `timezone.now`), so lease boundaries are really tested. Add a boundary test: `next_attempt_at == now`.
8. **Real Redis test (P1).** Add one test with the real Redis broker, not eager: publish -> assert the
   message is in the Redis queue (LLEN) -> start a worker (`celery.contrib.testing.worker.start_worker`) ->
   row SENT. Use Redis DB index 8. Keep the broker-crash test as a simulation and say so in the README;
   delete the "Redis 6.2.14 on DB 8" claim unless this test proves it.
9. **Observability (P1).** Add an `OutboxAttempt` model + migration (message FK, attempt_no, started_at,
   outcome, error). Write one row per attempt. The README guide shows the SQL to list failed attempts,
   and the operator command prints the history.

## task03_court_report  (P0, has a real bug)

1. **BUG: untagged bookings.** The tags query uses `values_list("court_id","tags__name").distinct()` (a
   LEFT JOIN), which yields `None`. Filter `tags__isnull=False`. Test: one court with a tagged and an
   untagged confirmed booking, one court with only untagged ones, and an empty court. Assert
   `naive == optimized` row by row (tags `[]` for the all-untagged court).
2. **Query counts must be asserted, not narrated.** On a 50-court fixture assert exact numbers with
   `django_assert_num_queries`: optimized == 4 (or the real number, but <= 5), naive == the formula you
   print in the README. Assert the row VALUES for all 50 rows, not just `len`.
3. **Pagination:** out-of-range page -> clamp to the last page or raise a clear `ValueError`; cap
   `page_size` (max 100). Test both.
4. **Mutations:** replace the infra-only ones with business ones: drop `distinct=True`; `__lte`->`__lt`
   on the end date; drop the `confirmed` filter; drop the `successful` filter. Name the catching tests.
5. **Seed:** `court = i % 20` and `confirmed = i % 5 != 0` are correlated, so some courts never get a
   confirmed booking. Decouple them (e.g. a different modulus or a seeded `random.Random`). Make the seed
   idempotent (`--reset`, or skip if the data exists).
6. **EXPLAIN ANALYZE:** add the real 50-court page with a realistic date range on the 100k seed. In the
   README state honestly which indexes the plan uses. If `payment_booking_success_idx` or
   `booking_start_idx` are unused, say so, or change the index to one the plan uses. Remove the 9.45s
   claim unless reproduced.

## task09_cancellation_tests  (P0, a weak test)

1. **The atomicity test passes for the wrong reason.** Rewrite `test_spec_document_write_failure_rolls_back`:
   `transaction=True`; the document writer must CREATE the `RefundDocument` and then raise; afterwards,
   through a separate connection, the reservation is still `confirmed` and there are 0 documents.
2. Make deliberate defect 3 = "remove `transaction.atomic()`" (keep the spec's 3 defects), and update
   `mutation_check.py`. Re-verify that the named test catches each of the 3, for the right reason.
3. **Clock:** the service must take `now` (default `timezone.now()`); the test must patch the real clock
   that the service uses. Add a test that fails if the service reads any other clock.
4. A `cancelled` reservation with no `RefundDocument` on replay -> raise an explicit
   `InconsistentStateError` (not `DoesNotExist`). Test it.
5. Delete `test_spec_three_deliberate_defects_are_defined` (tautological) and the duplicate
   "simulates document-writing failure" test.

## task05_last_seat_reservation  (P1)

1. **Rollback test:** `transaction=True`; inject the failure AFTER `_insert` returns (add a small seam if
   needed); verify through a separate connection that 0 rows exist and the capacity is free; then a normal
   reserve succeeds.
2. **Cross-class key race (the spec's 409 path):** 2 classes, same user, same key, barrier, real
   connections -> exactly 1 success and 1 409, and 1 row. This exercises the unique-constraint
   `IntegrityError` path for real. Keep the monkeypatch test only as a unit test of the re-read branch.
3. Barrier after the connection is open (rule 15). Keep connections open until the PID assertion.
4. Unknown `class_id` -> a defined `ClassNotFound` error (map to 404 in the README). Test it.
5. Keep the README lock-order text, but add behavioural proof: the existing tests plus the test above.
   Demote the source-grep test to an extra check.

## task06_jwt_branch_access  (P1)

1. **Input validation:** login/refresh/logout bodies via a serializer or isinstance checks. A non-dict body or
   non-string fields -> 400, never 500. Test with a list body, `null`, and `{"username": 1}`.
2. **Logout:** use the claims already verified by the auth class (no second decode). Also accept the
   refresh token in the body so a client with an expired access token can still close its session; an
   expired/invalid token -> 401, never 500. Tests for both.
3. **Logging:** do not log the raw username. Log the user id after success, or a truncated `repr` capped at
   64 chars. Keep the token-never-logged test.
4. **Tests to add:** expired refresh token over HTTP -> 401; refresh token used as a Bearer access token ->
   401; refreshing session 1 leaves session 2 valid; a rate-limit test with real processes
   (`multiprocessing`, spawn) against real Redis.
5. Settings: `ALLOWED_HOSTS` from env; reject a `JWT_SECRET_KEY` shorter than 32 bytes. README: state the
   trade-offs (refresh reuse revokes the whole session; per-account throttling allows a 60s lockout by a
   third party; a correct password is rejected while locked). These are spec-conformant, so document them.
   Don't change them.

## task04_goods_transfer_api  (P1)

1. Make the role matrix true to the README: add the `no_profile_user` row (6 actors x 6 actions = 36) or
   correct the README to the real count (rule 13).
2. Add tests: a second employee of the same destination calling submit -> 403; an employee creating for a
   different destination -> 403.
3. Stable ordering: rows with IDENTICAL `created_at`, pages of size 2; assert strict `-id` order across pages
   and no duplicates or gaps. Mutation: drop `-id` -> this test fails.
4. Remove or justify the unreachable `created_by_id == user.pk` guard (creators are employees, deciders are
   managers). If kept, add a test that reaches it. Delete the structural tautology test.
5. Settings: fail closed when `SECRET_KEY` is unset (as task 6 does); `ALLOWED_HOSTS` from env. Cache
   `staff_for` per request.
6. README Assumptions (mark ⚠): the manager sees submitted, approved and rejected requests (needed for the
   409 on a second decision); the spec says "submitted".

## task07_debtors_refactor  (P2)

Prove the defect claims: parametrize the suite over `impl in {legacy, services}`. The regression
(happy-path) tests must pass on both. Each `test_spec_defect_*` must be `xfail(strict=True)` on legacy and
pass on services. Update the README to say this is what the red/green evidence is.

## task10_erp_architecture  (P1, design flaw)

Edit the README, then update `doc_rules.py` and the tests.
1. **Hot-court math is inconsistent.** It uses a 4 ms critical section but also 10 ms DB time per write. A
   transaction-level advisory lock is held until commit, so the hold time is >= 10 ms and rho = 150 x 0.010 =
   1.5 (unstable). Redesign: no advisory lock through the whole transaction. Rely on the exclusion
   constraint, and add a fast-fail path: a Redis `SET NX` gate per (court, interval) with a 10-minute TTL
   before the DB, so losers are rejected without a write. Recompute: only winners pay the 10 ms write;
   rejected requests cost about 1-2 ms. Show the arithmetic. (Verify before writing that
   `INSERT ... ON CONFLICT DO NOTHING` without a conflict target handles exclusion-constraint violations
   on PostgreSQL 16; otherwise catch the violation in the application.)
2. **Cache:** invalidate-on-every-change at 150 writes/s makes the hot court uncacheable. Use a 1-2 s TTL
   with single-flight refresh (stale-while-revalidate) for hot courts. Define the hit-rate alert per
   non-hot court.
3. **Inline expiry:** the insert path first runs `UPDATE reservation SET status='expired' WHERE court_id=? AND
   status='held' AND expires_at <= now() AND reserved_interval && ?` in the same transaction. The sweeper
   becomes cleanup only. Fix the sequence diagram so that B sends a NEW request that triggers the inline
   expiry. Today B "takes the interval" with no request, and the interval is blocked until the sweeper runs.
4. **Late-payment sample:** state the interpretation under Assumptions ("confirmed" = the provider
   captured the money). Add the branch where the interval is still free: the policy is refund (default)
   or re-confirm. Keep the step table (status/money/message/reconciliation). Add: callback signature check,
   amount-vs-reservation check, a `CALLBACK_EVENT` dedupe key, and matching against the provider
   settlement file.
5. ERD: add the user/role/branch-membership and report-aggregate tables the API relies on. Fix the
   "no unpartial overlap" wording.
6. Add a README note that the doc tests are structure checks only. Add rules to `doc_rules.py`: the doc
   must contain "inline expiry", must not contain "4 ms critical section", and must state rho for the hot
   court. Update the mutation record with the new checks.

## Root files
- `docs/STATUS.md`: reset per Part 3 below, then update after each task.
- `README.md` (root): regenerate the table's status/test counts from real runs only.
- `docs/PLAN.md` / `ENGINEERING_PLAN.md`: add a short "Round 2" section that links to this brief, and delete
  statements the code no longer satisfies.
- Review the `.opencode/commands/review.md` and `verify.md` checklists: add rules 10-16 as review items.
- Confirm the repo has a `.git` with the history the STATUS claims. If it does not, say so in STATUS and
  do not claim clean-clone or push results.

## Done criteria (orchestrator runs these, not subagents)
For every task: `ruff format . && ruff check . && ruff format --check . && pytest -q` green; coverage still
100% for tasks 1, 2, 9; each new test shown red before the fix (pasted in the README); the mutation table
valid per rule 11; README numbers reproducible (rule 13). Final report: per task, the files changed, the
commands run with real output tails, and anything not reproduced or not done.