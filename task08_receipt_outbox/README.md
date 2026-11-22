# Task 8 — Recoverable receipt dispatch (transactional outbox)

A payment and its receipt `OutboxMessage` are committed in one PostgreSQL transaction;
`transaction.on_commit` publishes a Celery task, and a beat sweeper re-enqueues due rows so a
broker crash after commit cannot lose the receipt. The external service is replaced by a
deterministic Fake with four modes; idempotency keys and a 30 s dispatch lease make repeated
sends safe, and failed rows can be re-pursued by an operator.

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

`db_utils.ensure_database()` is the single implementation used by both the `ensure_db`
command and the pytest session fixture. Verified from a dropped `task08` database:
`ensure_db` → `database task08 is ready`, `migrate` → `Applying receipts.0001_initial... OK`,
and all four `receipts_*` tables present. Create a payment with
`.venv/bin/python manage.py shell -c "from receipts.services import record_payment; print(record_payment('demo-1', 12000).pk)"`.
Celery uses Redis database index **8** as broker and result backend; beat calls
`receipts.tasks.sweep_outbox` every **5 s**.

## Test

```bash
cd task08_receipt_outbox
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q
```

Real measured result (PostgreSQL **16.2** via unix socket, Redis **6.2.14** on DB 8):
final quality gate `32 passed in 2.43s`; five consecutive runs earlier gave `32 passed` in
1.66–1.80 s. Every test is
transactional (`django_db(transaction=True)` where `on_commit` must fire), uses a global
20 s timeout, and the concurrency tests carry their own 30 s timeouts and `threading.Barrier`.

## Fake worker contract

`set_fake_mode(mode)` (or `FakeReceiptService(mode=...)`) selects one of:

| Mode | Behavior |
| --- | --- |
| `ok` | Stores one `FakeExternalMessage` per key and returns its id; repeats return the same id. |
| `temporary_error` | Raises `TemporaryReceiptError`; nothing is accepted. |
| `permanent_error` | Raises `PermanentReceiptError`; nothing is accepted and dispatch stops. |
| `accept_then_timeout` | Stores the message, then raises `ReceiptTimeoutError` (response lost). |

`lookup(key)` returns the stored message id if a timed-out send was in fact accepted.
Acceptance uses `get_or_create` on the unique key, so 12 concurrent sends for one key produce
one external message and one shared id (no `IntegrityError`). The autouse fixture resets the
mode to `ok` after every test.

## Recovery path

1. `record_payment()` validates the amount, then inserts `Payment` + `OutboxMessage` in one
   `transaction.atomic()`; the publish is registered with `transaction.on_commit`.
2. `_enqueue()` catches `kombu.exceptions.OperationalError` and `redis.exceptions.ConnectionError`,
   logs a warning and returns. The committed row is never lost; the next sweep delivers it.
3. `dispatch_receipt(message_id)` locks the row (`select_for_update`), and if it is a fresh
   pending row increments `attempts`, sets `in_progress`, and pushes `next_attempt_at` to
   `now + LEASE_SECONDS` (30 s). That lease stops beat (5 s ticks) from re-claiming a slow send;
   the slow-dispatch test sweeps five times mid-send and `attempts` stays **1**.
4. A second worker that finds `in_progress` while the lease is live returns immediately; two
   workers started on a barrier never both call `send`. A stale `in_progress` row (crashed
   worker) is re-claimed with a renewed lease **without** burning another attempt.
5. `claim_due_messages(now)` selects due `pending`/`in_progress` rows with
   `select_for_update(skip_locked=True)` and enqueues each one; it deliberately does not write
   status or lease, so the task that actually dispatches owns the lease.
6. Temporary errors retry at `now + 2^(attempts-1)` seconds — measured schedule
   **+1 s, +2 s, +4 s, +8 s**, five attempts total; the fifth failure sets `failed`.
   Permanent errors set `failed` on the first attempt.
7. A timeout calls `lookup(key)`; if the message was accepted the local receipt is written
   immediately. Crash-after-send recovery reuses the same idempotency key, so the repeat send
   returns the existing external message and creates no duplicate receipt.
8. Operator retry: `.venv/bin/python manage.py retry_receipt_dispatch <message_id>` works only
   on `failed` rows; any other state raises
   `CommandError: ... is <state>; only failed rows can be retried` and changes nothing.

## Observing failed attempts

Failed and retrying rows keep `attempts`, `last_error` and `next_attempt_at` in PostgreSQL:

```python
from receipts.models import OutboxMessage

list(
    OutboxMessage.objects.filter(status="failed").values(
        "id", "attempts", "last_error", "next_attempt_at"
    )
)
list(
    OutboxMessage.objects.filter(status="pending", attempts__gt=0)
    .order_by("next_attempt_at")
    .values("id", "attempts")
)
```

In production, run those queries in `manage.py dbshell` (or the Django shell); the
`retry_receipt_dispatch` command prints `requeued outbox message <id>` for each retry.
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
| `select_for_update(skip_locked=True)` | `test_spec_select_for_update_skip_locked_claiming` |
| Idempotency key | `test_spec_idempotency_key_sent_to_external_service` |
| 5 attempts, increasing intervals | `test_spec_temporary_error_retries_five_times_with_increasing_intervals` |
| Permanent error stops | `test_spec_permanent_error_stops_immediately` |
| Operator retry / failed-state guard | `test_spec_operator_retry_dispatches_failed_dispatch`, `test_spec_operator_retry_requires_failed_state` |
| Timeout after accept | `test_spec_timeout_after_accept_gives_one_external_message_and_one_receipt` |
| Crash between sent and recorded | `test_spec_crash_between_sent_and_recorded` |
| Slow dispatch does not consume attempts | `test_spec_slow_dispatch_does_not_consume_attempts` |
| Stale re-claim does not increment attempts | `test_spec_reclaim_does_not_increment_attempts` |
| Two workers, one payment (barrier) | `test_spec_two_workers_one_payment`, `test_spec_two_workers_never_process_same_message` |
| Fake accepts one message per key under concurrency | `test_spec_fake_service_concurrent_send_creates_one_message`, `test_spec_fake_worker_contract_modes` |
| Reject float/non-integer amounts | `test_spec_rejects_float_and_non_integer_amounts` |
| Failed attempts observable / config / money and UTC | `test_spec_failed_attempts_observable`, `test_spec_redis_broker_and_postgres_durable_state`, `test_spec_money_integer_rial_and_utc_timestamps` |

## Mutation spot-check

Each mutation was applied, the named test was run, and the code was reverted:

1. Removed the lease write (`next_attempt_at = moment + timedelta(seconds=LEASE_SECONDS)`) in
   `process_outbox_message()` → `test_spec_slow_dispatch_does_not_consume_attempts` failed with
   `datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc) == (... + 30 s)` in 5.29 s.
2. Removed the `try/except` around `dispatch_receipt.delay()` in `_enqueue()` →
   `test_spec_broker_down_after_commit_sweeper_recovers` failed with
   `redis.exceptions.ConnectionError: broker down` propagating out of `record_payment()`.
3. Restored `FakeExternalMessage.objects.create(...)` in `FakeReceiptService._accept()` →
   `test_spec_fake_service_concurrent_send_creates_one_message` failed with 9 collected
   `IntegrityError('duplicate key value violates unique constraint "receipts_fakeexternalmessage_idempotency_key_key"')`.

## Assumptions

- Integer rial is stored in `BigIntegerField`; only `int` and whole `Decimal` values are
  accepted, and `float`, `str`, `bool`, `None` or fractional `Decimal` raise a clear `ValueError`.
  Timestamps are timezone-aware UTC (`USE_TZ = True`).
- `LEASE_SECONDS = 30` covers several beat ticks; a crashed dispatch is recoverable once the
  lease expires. Recovery is intentionally not instantaneous.
- The Fake's message store lives in the same test database as a test instrument; a real
  deployment would call a separate HTTP service with the same idempotency contract.
- `accept_then_timeout` plus a failed `lookup` is treated as retryable; the stored message is
  found by the next idempotent send.
- Real Redis is configured at DB 8, but the tests run Celery eagerly with a propagating broker;
  the broker-outage test injects the exact Redis `ConnectionError` at `.delay()`.

## Unfinished parts

- No separate admin action (the required operator path is the management command).
- No dead-letter queue or operational dashboard beyond the ORM query guide above.
- Celery worker/beat process supervision is left to the environment.
