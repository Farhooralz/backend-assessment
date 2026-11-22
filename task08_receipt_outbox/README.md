# Task 8 — Recoverable receipt dispatch (transactional outbox)

A payment and its receipt `OutboxMessage` are committed in one PostgreSQL transaction;
`transaction.on_commit` enqueues a Celery task, and a Celery beat sweeper also claims due
rows so a broker crash after commit cannot lose the receipt. The external receipt service
is replaced by a deterministic Fake with four modes; idempotency keys make repeated sends
safe, and failed rows can be re-pursued by an operator.

## Run

Load the shared environment first; the settings read `POSTGRES_HOST`, `POSTGRES_PORT`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_HOST` and `REDIS_PORT` with `os.environ`.
The fallback Postgres host is a unix-socket directory and the port/password are empty
strings, which are passed through unchanged.

```bash
cd task08_receipt_outbox
set -a; . ../.env; set +a
.venv/bin/python manage.py migrate --run-syncdb
.venv/bin/celery -A celery_app worker -l info
# in a second shell, same env:
set -a; . ../.env; set +a
.venv/bin/celery -A celery_app beat -l info
```

Create a payment from a shell with
`.venv/bin/python manage.py shell -c "from receipts.services import record_payment; print(record_payment('demo-1', 12000).pk)"`.
Celery uses Redis (database index **8**) as broker and result backend; PostgreSQL database
`task08` is the durable store. Beat invokes `receipts.tasks.sweep_outbox` every **5 s**.

## Test

```bash
cd task08_receipt_outbox
set -a; . ../.env; set +a; .venv/bin/python -m pytest -q
```

Real measured result (PostgreSQL **16.2** via unix socket, Redis **6.2.14** via DB 8,
both reachable):
`20 passed in 1.66s`. `conftest.py` creates `task08` with `psycopg` if absent;
pytest-django then creates `test_task08`. Celery runs eagerly in tests while the
configured broker remains Redis. Every test is transactional (`django_db(transaction=True)`
where `on_commit` must fire) and has a 20 s global timeout.

## Fake worker contract

`set_fake_mode(mode)` (or `FakeReceiptService(mode=...)`) selects one of:

| Mode | Behavior |
| --- | --- |
| `ok` | Stores one `FakeExternalMessage` per key and returns its id; repeats return the same id. |
| `temporary_error` | Raises `TemporaryReceiptError`; nothing is accepted. |
| `permanent_error` | Raises `PermanentReceiptError`; nothing is accepted and dispatch stops. |
| `accept_then_timeout` | Stores the message, then raises `ReceiptTimeoutError` (response lost). |

`lookup(key)` returns the stored message id if a timed-out send was in fact accepted.
Tests reset the mode to `ok` after every test.

## Recovery path

1. `record_payment()` inserts `Payment` + `OutboxMessage` in one `transaction.atomic()`;
   the enqueue is registered with `transaction.on_commit`.
2. `dispatch_receipt(message_id)` locks the row (`select_for_update`), increments
   `attempts`, calls the Fake with the stable key `receipt:<reference>`, and creates one
   local `Receipt` (`get_or_create`, unique per outbox).
3. `sweep_outbox(now)` claims due `pending`/`in_progress` rows with
   `select_for_update(skip_locked=True)` and re-enqueues them. This is the recovery when
   the broker crashes after commit or a worker dies mid-dispatch.
4. Temporary errors retry at `now + 2^(attempts-1)` seconds: measured schedule
   **+1 s, +2 s, +4 s, +8 s**, five attempts total; the fifth failure sets `failed`.
   Permanent errors set `failed` on the first attempt.
5. A timeout first calls `lookup(key)`; if the message was accepted, the local receipt is
   written immediately. Crash-after-send recovery uses the same idempotency key, so the
   repeat send returns the existing external message and creates no duplicate receipt.
6. Operator retry: `.venv/bin/python manage.py retry_receipt_dispatch <message_id>`
   resets `attempts`, status and `next_attempt_at` and enqueues again under the same key.

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
timeout/crash tests prove there is exactly one external message.

## Spec/test map

| Spec item | Test |
| --- | --- |
| Payment and outbox in one transaction | `test_spec_payment_and_outbox_row_in_one_transaction` |
| Rollback creates no message | `test_spec_rollback_creates_no_message` |
| `on_commit` triggers Celery | `test_spec_on_commit_triggers_celery_dispatch` |
| Broker crash after commit | `test_spec_broker_crash_after_commit_keeps_receipt` |
| Periodic sweeper | `test_spec_periodic_sweeper_only_claims_due_rows` |
| `select_for_update(skip_locked=True)` | `test_spec_select_for_update_skip_locked_claiming` |
| Idempotency key | `test_spec_idempotency_key_sent_to_external_service` |
| 5 attempts, increasing intervals | `test_spec_temporary_error_retries_five_times_with_increasing_intervals` |
| Permanent error stops | `test_spec_permanent_error_stops_immediately` |
| Operator retry | `test_spec_operator_retry_dispatches_failed_dispatch` |
| Timeout after accept | `test_spec_timeout_after_accept_gives_one_external_message_and_one_receipt` |
| Crash between sent and recorded | `test_spec_crash_between_sent_and_recorded` |
| Two workers, one payment | `test_spec_two_workers_one_payment` |
| Fake contract / observability / config / money and UTC | `test_spec_fake_worker_contract_modes`, `test_spec_failed_attempts_observable`, `test_spec_redis_broker_and_postgres_durable_state`, `test_spec_money_integer_rial_and_utc_timestamps` |

## Mutation spot-check

Each mutation was applied, the named test was run, and the code was reverted:

1. Removed `skip_locked=True` from `claim_due_messages()` →
   `test_spec_select_for_update_skip_locked_claiming` failed with `assert [1] == []`
   in 5.29 s (the waiting claim took the locked row).
2. Changed `MAX_ATTEMPTS` from 5 to 4 →
   `test_spec_temporary_error_retries_five_times_with_increasing_intervals` failed on the
   fourth interval (`12:00:07 != 12:00:15`).
3. Replaced `Receipt.objects.get_or_create(...)` with `create(...)` →
   `test_spec_two_workers_one_payment` failed with
   `duplicate key value violates unique constraint "receipts_receipt_outbox_id_key"`.

## Assumptions

- Integer rial is stored in `BigIntegerField`; `Decimal` input is converted to `int` on
  entry. Timestamps are timezone-aware UTC (`USE_TZ = True`).
- `MIGRATION_MODULES = {"receipts": None}` keeps this standalone task migration-free;
  `migrate --run-syncdb` creates the tables.
- The Fake's message store lives in the same test database as a test instrument; a real
  deployment would call a separate HTTP service with the same idempotency contract.
- `accept_then_timeout` plus a failed `lookup` is treated as retryable; the stored message
  is found by the next idempotent send.

## Unfinished parts

- No separate admin action (the required operator path is the management command).
- No dead-letter queue or operational dashboard beyond the ORM query guide above.
- Celery worker/beat process supervision is left to the environment.
