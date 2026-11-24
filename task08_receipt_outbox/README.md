# Task 8 — Recoverable receipt dispatch (transactional outbox)

A payment and its receipt `OutboxMessage` are committed in one PostgreSQL transaction;
`transaction.on_commit` publishes a Celery task, and a beat sweeper re-enqueues due rows so a
broker crash after commit cannot lose the receipt. The external service is replaced by a
deterministic Fake with four modes. Row locks, a lease/backoff check, stale-worker detection and
the idempotency key make duplicate tasks and late workers harmless; every dispatch attempt is
recorded in `OutboxAttempt` and an operator can re-pursue a failed row.

## Run

Load the shared environment first; settings read `POSTGRES_HOST`, `POSTGRES_PORT`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_HOST` and `REDIS_PORT` with `os.environ`.
The fallback Postgres host is a unix-socket directory and port/password are empty strings,
passed through unchanged. `ensure_db` is idempotent, so this sequence works on a clean clone:

```bash
cd task08_receipt_outbox
set -a; . ../.env; set +a
.venv/bin/python manage.py ensure_db && .venv/bin/python manage.py migrate
.venv/bin/celery -A celery_app worker -l info
# in a second shell, same env:
set -a; . ../.env; set +a
.venv/bin/celery -A celery_app beat -l info
```

Create a payment with
`.venv/bin/python manage.py shell -c "from receipts.services import record_payment; print(record_payment('demo-1', 12000).pk)"`.
Celery uses Redis database index **8** as broker and result backend; beat calls
`receipts.tasks.sweep_outbox` every **5 s**. The real-Redis test below asserts the broker URL
and queue contents; the current versions can be printed with:

```bash
set -a; . ../.env; set +a; .venv/bin/python -c \
"import os,redis,psycopg; from db_utils import pg_params; \
r=redis.Redis(host=os.environ.get('REDIS_HOST','127.0.0.1'),port=int(os.environ.get('REDIS_PORT','6379')),db=8); \
print(r.info('server')['redis_version']); \
c=psycopg.connect(**pg_params('postgres')); print(c.execute('SHOW server_version').fetchone()[0])"
```

Measured with that command: Redis **6.2.14** on DB 8, PostgreSQL **16.2**.

## Test

```bash
cd task08_receipt_outbox
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q
```

Latest final run: `47 passed`. `pytest --collect-only -q | tail -1` prints
`47 tests collected`. All tests use the shared `../.env`, a global timeout from `pytest.ini`,
and a real PostgreSQL test database `test_task08`; the concurrency tests carry their own
timeouts and `threading.Barrier`.

## Fake worker contract

`set_fake_mode(mode)` (or `FakeReceiptService(mode=...)`) selects one of:

| Mode | Behavior |
| --- | --- |
| `ok` | Stores one `FakeExternalMessage` per key and returns its id; repeats return the same id. |
| `temporary_error` | Raises `TemporaryReceiptError`; nothing is accepted. |
| `permanent_error` | Raises `PermanentReceiptError`; nothing is accepted and dispatch stops. |
| `accept_then_timeout` | Records the message, then raises `ReceiptTimeoutError` (response lost). |

`lookup(key)` returns the stored message id if a timed-out send was in fact accepted; it is
never patched in the spec-sample test. Acceptance uses `get_or_create` on the unique key, so
**12** concurrent sends for one key produce one external message and one shared id
(`test_spec_fake_service_concurrent_send_creates_one_message`). The autouse fixture resets the
mode to `ok` after every test.

## Recovery path

1. `record_payment()` validates the amount, then inserts `Payment` + `OutboxMessage` in one
   `transaction.atomic()`; `enqueue_dispatch()` is registered with `transaction.on_commit`.
2. `enqueue_dispatch()` catches `kombu.exceptions.OperationalError` and
   `redis.exceptions.ConnectionError`, logs a warning and returns. The committed row is never
   lost; the next sweep delivers it.
3. `dispatch_receipt(message_id)` locks the row. If `next_attempt_at` is still in the future it
   returns immediately: this is either backoff (PENDING) or a live dispatch lease
   (IN_PROGRESS), and no attempt is consumed and no send happens. Otherwise it increments
   `attempts`, renews the `LEASE_SECONDS = 30` lease, and writes one `OutboxAttempt` row.
4. Before `_defer`, `_fail` and the SENT write, the row is locked again and the worker must
   still see `IN_PROGRESS` with its own `attempts`; otherwise it returns the current status
   without writing. `record_receipt()` and the SENT update happen in one `transaction.atomic()`
   with the attempt outcome.
5. Re-claiming an expired lease (crashed worker) **is** a new attempt and is capped: an attempt
   beyond `MAX_ATTEMPTS = 5` sets `failed` with `last_error = "worker crashed repeatedly"`.
6. `claim_due_messages(now)` selects due `pending`/`in_progress` rows with
   `select_for_update(skip_locked=True)`; the lock is released when that transaction commits,
   **before** enqueue. Two sweepers can therefore enqueue the same id. Duplicates are harmless
   because of (a) the task's row lock, (b) the lease/backoff checks, (c) the idempotency key.
   The claim itself is read-only.
7. Temporary errors retry at `now + 2^(attempts-1)` seconds — measured schedule
   **+1 s, +2 s, +4 s, +8 s**, five attempts total; the fifth failure sets `failed`.
   Permanent errors set `failed` on the first attempt.
8. A timeout calls `lookup(key)`: if the Fake recorded the message, the receipt is written and
   the row becomes `sent`; if lookup misses, the row defers and the retry resends with the same
   key, producing no second external message. Crash-after-send recovery follows the same path:
   the external message exists but no local receipt does, so the retry reuses the key.
9. Operator retry: `.venv/bin/python manage.py retry_receipt_dispatch <message_id>` works only
   on `failed` rows; any other state raises
   `CommandError: ... is <state>; only failed rows can be retried` and changes nothing. It uses
   the same `enqueue_dispatch()` helper as the sweeper (a broker outage leaves the row PENDING
   for the sweeper) and prints the attempt history.

## Real Redis broker test

`test_spec_real_redis_broker_worker_marks_row_sent` runs with `CELERY_TASK_ALWAYS_EAGER = False`,
publishes with `dispatch_receipt.delay()`, asserts the queue length with Redis `LLEN` on DB 8,
then runs `celery.contrib.testing.worker.start_worker` and waits for the row to become `sent`.
All other tests run Celery eagerly. The broker-crash tests inject the exact Redis
`ConnectionError` at `.delay()`; they are **simulations**, not a real broker outage.

## Observing failed attempts

One `OutboxAttempt` row is written per claim (outcome `in_progress` until finalized to
`sent` / `deferred` / `failed`), in the same transaction as the state change. A worker that
crashes after claiming leaves an `in_progress` row — a useful stuck-worker signal. SQL for
`manage.py dbshell`:

```sql
SELECT m.id, a.attempt_no, a.started_at, a.outcome, a.error
FROM receipts_outboxattempt a
JOIN receipts_outboxmessage m ON m.id = a.message_id
WHERE a.outcome IN ('failed', 'deferred')
ORDER BY a.started_at DESC;
```

Equivalent Django query and operator output:

```python
from receipts.models import OutboxAttempt

list(OutboxAttempt.objects.filter(outcome="failed").values("message_id", "attempt_no", "error"))
```

```text
requeued outbox message <id>
  attempt 1: failed at 2026-02-01T09:00:00+00:00 (permanent: permanent receipt rejection)
```

`FakeExternalMessage` shows what the external service actually accepted, which is how the
timeout and crash tests prove there is exactly one external message.

## Spec/test map

| Spec item | Test |
| --- | --- |
| Payment and outbox in one transaction | `test_spec_payment_and_outbox_row_in_one_transaction` |
| Rollback creates no message | `test_spec_rollback_creates_no_message` |
| `on_commit` triggers Celery | `test_spec_on_commit_triggers_celery_dispatch` |
| Broker down after commit → sweeper recovers one message + one receipt | `test_spec_broker_down_after_commit_sweeper_recovers` |
| Real migration / `ensure_db` reproducibility | `test_spec_real_migration_creates_tables`, `test_spec_ensure_database_is_idempotent_and_exposed_as_command` |
| Periodic sweeper only claims due rows | `test_spec_periodic_sweeper_only_claims_due_rows` |
| `skip_locked` skips a row held by another transaction | `test_spec_skip_locked_skips_row_held_by_other_transaction` |
| Claims are read-only / duplicates are harmless | `test_spec_claim_due_messages_does_not_write_state`, `test_spec_duplicate_sweep_enqueues_send_once` |
| Backoff is not bypassed / boundary is inclusive | `test_spec_pending_row_with_future_next_attempt_is_not_processed_early`, `test_spec_duplicate_task_after_temporary_failure_does_not_send`, `test_spec_next_attempt_at_boundary_is_inclusive` |
| Idempotency key | `test_spec_idempotency_key_sent_to_external_service` |
| 5 attempts, increasing intervals | `test_spec_temporary_error_retries_five_times_with_increasing_intervals` |
| Permanent error stops | `test_spec_permanent_error_stops_immediately` |
| Operator retry / failed-state guard / broker outage | `test_spec_operator_retry_dispatches_failed_dispatch`, `test_spec_operator_retry_requires_failed_state`, `test_spec_operator_retry_broker_down_leaves_pending_for_sweeper` |
| Timeout after accept (lookup NOT patched) / lookup misses | `test_spec_timeout_after_accept_gives_one_external_message_and_one_receipt`, `test_spec_timeout_with_missing_lookup_retry_resends_safely` |
| Stale worker cannot overwrite SENT / receipt+SENT are atomic | `test_spec_stale_worker_defer_cannot_overwrite_sent`, `test_spec_receipt_and_sent_write_roll_back_together` |
| Crash loop cap | `test_spec_crash_reclaim_beyond_max_attempts_fails`, `test_spec_reclaim_increments_attempts_after_crash` |
| Crash between sent and recorded | `test_spec_crash_between_sent_and_recorded` |
| Slow dispatch / stale re-claim | `test_spec_slow_dispatch_does_not_consume_attempts`, `test_spec_frozen_clock_drives_sweep_and_task_lease_boundary` |
| Two workers, one payment (barrier) | `test_spec_two_workers_one_payment`, `test_spec_two_workers_never_process_same_message` |
| Fake accepts one message per key under concurrency | `test_spec_fake_service_concurrent_send_creates_one_message`, `test_spec_fake_worker_contract_modes` |
| Reject float/non-integer amounts | `test_spec_rejects_float_and_non_integer_amounts` |
| Observability / one clock / config / money and UTC | `test_spec_attempt_history_records_one_row_per_attempt`, `test_spec_operator_command_prints_attempt_history`, `test_spec_failed_attempts_observable`, `test_spec_redis_broker_and_postgres_durable_state`, `test_spec_money_integer_rial_and_utc_timestamps` |
| Real broker, non-eager worker | `test_spec_real_redis_broker_worker_marks_row_sent` |

## Round 2

Red-first proof, before any implementation change:
`set -a; . ../.env; set +a; .venv/bin/python -m pytest -q --tb=line` →
`12 failed, 35 passed`. Exact failure lines (line numbers from the pre-fix files):

```text
test_receipt_outbox.py:367: AssertionError: assert ('receipts', '0002_outboxattempt') in {('receipts', '0001_initial'): <Migration receipts.0001_initial>}
test_receipt_outbox.py:451: assert 1 == 2
test_round2_fixes.py:64: AssertionError: assert OutboxMessage.Status.SENT == 'pending'
test_round2_fixes.py:104: assert 2 == 1
test_round2_fixes.py:127: AssertionError: assert True is False
test_round2_fixes.py:171: AssertionError: assert 'pending' == 'sent'
test_round2_fixes.py:199: assert 1 == 0
test_round2_fixes.py:221: AssertionError: assert OutboxMessage.Status.SENT == 'failed'
unittest/mock.py:1198: redis.exceptions.ConnectionError: broker down
test_round2_fixes.py:318: assert 1 == 2
test_round2_fixes.py:366: LookupError: App 'receipts' doesn't have a 'OutboxAttempt' model.
test_round2_fixes.py:387: LookupError: App 'receipts' doesn't have a 'OutboxAttempt' model.
```

Finding-by-finding outcome:

1. **Backoff bypass — reproduced and fixed.** Added the `next_attempt_at > moment` guard in
   `process_outbox_message()`. Evidence above (lines 64, 104, 127).
2. **Stale worker — reproduced and fixed.** `_relock_claim()` is used before `_defer`, `_fail`
   and the SENT write; `record_receipt()` and the SENT update share one `transaction.atomic()`.
   Evidence above (lines 171, 199).
3. **Crash loop cap — reproduced and fixed.** Re-claiming increments `attempts`; beyond five it
   fails with `worker crashed repeatedly`. Evidence above (line 221 and
   `test_receipt_outbox.py:451`). `test_spec_reclaim_does_not_increment_attempts` was deliberately
   updated to `test_spec_reclaim_increments_attempts_after_crash` (see Assumptions).
4. **Sweeper docs — not a code bug.** The `skip_locked` lock is released before enqueue; the old
   docstring/README claimed exclusive claims. `test_spec_claim_due_messages_does_not_write_state`
   passed before and after (it proves the claim is read-only), and
   `test_spec_skip_locked_skips_row_held_by_other_transaction` was renamed to say what it proves.
   Docs now state duplicates are possible and harmless.
5. **Operator retry — reproduced and fixed.** The command now calls `enqueue_dispatch()`;
   evidence above (`redis.exceptions.ConnectionError: broker down` escaping `call_command`).
6. **Spec sample — not reproduced as a bug, test strengthened.** The old test patched `lookup`
   to `None`, which hid the Fake's real accept-then-timeout path. It passed on the original code
   (part of the 35 green tests in the red run) and still passes without the patch. The
   lookup-misses variant is kept as a second test.
7. **One clock — boundary reproduced.** The `next_attempt_at = now + 1 µs` case was red
   (line 127) and is now green. `test_spec_frozen_clock_drives_sweep_and_task_lease_boundary`
   patches `timezone.now` and drives both sweep and task without explicit `now` (it was red at
   line 318 only because re-claim now counts an attempt).
8. **Real Redis — new deliverable, no bug reproduced.** The non-eager worker test passed on the
   original code too; it is a protocol test. The old "Redis 6.2.14 on DB 8" claim is now
   accompanied by the version command above and the queue assertion in this test.
9. **Observability — reproduced as missing.** The migration/model assertions above failed with
   `LookupError` and a missing `0002_outboxattempt`. Added the model, migration, one row per
   attempt, and history output in the operator command.

Final gate after all fixes: `ruff format . && ruff check . && ruff format --check . && pytest -q`
→ `All checks passed`, `20 files already formatted`, `47 passed`.

## Mutation spot-check (round 2)

Each mutation changed business logic, one named test was run, and the file was restored:

| Mutation (implementation) | Failing test (`file::test_name`) | Observed failure |
| --- | --- | --- |
| Remove the `next_attempt_at > moment` guard | `tests/test_round2_fixes.py::test_spec_pending_row_with_future_next_attempt_is_not_processed_early` | `assert OutboxMessage.Status.SENT == 'pending'` |
| Return the row from `_relock_claim()` without checking status/attempts | `tests/test_round2_fixes.py::test_spec_stale_worker_defer_cannot_overwrite_sent` | `assert 'pending' == 'sent'` |
| Disable the `attempts > MAX_ATTEMPTS` cap | `tests/test_round2_fixes.py::test_spec_crash_reclaim_beyond_max_attempts_fails` | `assert OutboxMessage.Status.SENT == 'failed'` |
| Publish directly with `dispatch_receipt.delay()` in the operator command | `tests/test_round2_fixes.py::test_spec_operator_retry_broker_down_leaves_pending_for_sweeper` | `redis.exceptions.ConnectionError: broker down` escapes `call_command` |
| Drop the `OutboxAttempt.objects.create()` at claim time | `tests/test_round2_fixes.py::test_spec_attempt_history_records_one_row_per_attempt` | `assert [] == [1, 2]` |
| Drop `next_attempt_at__lte=moment` from `claim_due_messages()` | `tests/test_receipt_outbox.py::test_spec_periodic_sweeper_only_claims_due_rows` | `assert 1 == 0` |

## Assumptions

- ⚠ Round-2 rule changes an earlier contract: re-claiming a stale `IN_PROGRESS` row now counts
  as an attempt, so `test_spec_reclaim_does_not_increment_attempts` became
  `test_spec_reclaim_increments_attempts_after_crash` and expects `attempts = 2`. A sixth such
  re-claim fails the message as `worker crashed repeatedly`.
- ⚠ `attempt_no` in `OutboxAttempt` is monotonic for a message, while `OutboxMessage.attempts`
  is the retry budget and is reset to zero by an operator retry. History rows are never deleted.
- Integer rial is stored in `BigIntegerField`; only `int` and whole `Decimal` values are
  accepted, and `float`, `str`, `bool`, `None` or fractional `Decimal` raise a clear `ValueError`.
  Timestamps are timezone-aware UTC (`USE_TZ = True`).
- `LEASE_SECONDS = 30` covers several beat ticks; a crashed dispatch is recoverable once the
  lease expires. Recovery is intentionally not instantaneous. The lease is compared with `>`,
  so `next_attempt_at == now` is due (inclusive boundary).
- The Fake's message store lives in the same test database as a test instrument; a real
  deployment would call a separate HTTP service with the same idempotency contract.
- `accept_then_timeout` plus a failed `lookup` is treated as retryable; the stored message is
  found by the next idempotent send.

## Unfinished parts

- No separate admin action (the required operator path is the management command).
- No dead-letter queue or operational dashboard beyond the SQL guide above.
- Celery worker/beat process supervision is left to the environment.
