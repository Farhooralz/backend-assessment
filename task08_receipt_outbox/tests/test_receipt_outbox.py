"""Spec-driven tests for the recoverable receipt dispatch (Task 8)."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from celery_app import app
from receipts import fake_service, services
from receipts.models import FakeExternalMessage, OutboxMessage, Payment, Receipt
from receipts.tasks import dispatch_receipt

T0 = timezone.make_aware(datetime(2026, 1, 1, 12, 0, 0), UTC)


def _create_pending(reference: str = "pay-1", *, now: datetime = T0) -> OutboxMessage:
    """Create a payment whose enqueue is suppressed, simulating a broker outage."""
    with monkeypatch_delay():
        services.record_payment(reference=reference, amount_rial=12000, now=now)
    return OutboxMessage.objects.get(payment__reference=reference)


class monkeypatch_delay:
    """Context manager that drops Celery enqueues until the block exits."""

    def __enter__(self) -> "monkeypatch_delay":
        self._original = dispatch_receipt.delay
        dispatch_receipt.delay = lambda *args, **kwargs: None
        return self

    def __exit__(self, *exc: object) -> None:
        dispatch_receipt.delay = self._original


@pytest.mark.django_db(transaction=True)
def test_spec_payment_and_outbox_row_in_one_transaction() -> None:
    payment = services.record_payment(reference="pay-atomic", amount_rial=Decimal("12000"), now=T0)
    outbox = OutboxMessage.objects.get(payment=payment)
    assert payment.amount_rial == 12000
    assert outbox.idempotency_key == "receipt:pay-atomic"
    assert outbox.payload == {"reference": "pay-atomic", "amount_rial": 12000}
    assert OutboxMessage.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_rollback_creates_no_message() -> None:
    with pytest.raises(RuntimeError, match="boom"), transaction.atomic():
        services.record_payment(reference="pay-rollback", amount_rial=1000, now=T0)
        raise RuntimeError("boom")

    assert Payment.objects.count() == 0
    assert OutboxMessage.objects.count() == 0
    assert FakeExternalMessage.objects.count() == 0
    assert Receipt.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_spec_on_commit_triggers_celery_dispatch() -> None:
    payment = services.record_payment(reference="pay-commit", amount_rial=500, now=T0)
    outbox = OutboxMessage.objects.get(payment=payment)
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert Receipt.objects.count() == 1
    assert FakeExternalMessage.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_broker_down_after_commit_sweeper_recovers(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broker_down(*args: object, **kwargs: object) -> None:
        raise redis.exceptions.ConnectionError("broker down")

    # The publish fails after the payment committed; the caller must not see the error.
    with monkeypatch.context() as patch:
        patch.setattr(dispatch_receipt, "delay", broker_down)
        payment = services.record_payment(reference="pay-broker-down", amount_rial=700, now=T0)

    outbox = OutboxMessage.objects.get(payment=payment)
    assert outbox.status == "pending"
    assert FakeExternalMessage.objects.count() == 0
    assert "broker down" in caplog.text

    services.sweep_outbox(now=T0)

    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_periodic_sweeper_only_claims_due_rows() -> None:
    outbox = _create_pending("pay-not-due", now=T0)
    OutboxMessage.objects.filter(pk=outbox.pk).update(next_attempt_at=T0 + timedelta(minutes=1))

    services.sweep_outbox(now=T0)
    assert FakeExternalMessage.objects.count() == 0

    services.sweep_outbox(now=T0 + timedelta(minutes=1))
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(10)
def test_spec_skip_locked_skips_row_held_by_other_transaction() -> None:
    outbox = _create_pending("pay-locked")
    entered = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        try:
            with transaction.atomic():
                OutboxMessage.objects.select_for_update().get(pk=outbox.pk)
                entered.set()
                release.wait(timeout=5)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    assert entered.wait(timeout=5)

    assert services.claim_due_messages(now=T0) == []

    release.set()
    holder.join(timeout=5)
    assert services.claim_due_messages(now=T0) == [outbox.pk]


@pytest.mark.django_db(transaction=True)
def test_spec_idempotency_key_sent_to_external_service() -> None:
    outbox = _create_pending("pay-idempotent")

    services.process_outbox_message(outbox.pk, now=T0)
    external = FakeExternalMessage.objects.get()
    assert external.idempotency_key == outbox.idempotency_key
    assert external.payload == outbox.payload

    services.process_outbox_message(outbox.pk, now=T0)
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_temporary_error_retries_five_times_with_increasing_intervals() -> None:
    fake_service.set_fake_mode("temporary_error")
    outbox = _create_pending("pay-temp")

    due_times = []
    current = T0
    for _ in range(4):
        services.process_outbox_message(outbox.pk, now=current)
        outbox.refresh_from_db()
        due_times.append(outbox.next_attempt_at)
        current = outbox.next_attempt_at

    assert due_times == [
        T0 + timedelta(seconds=1),
        T0 + timedelta(seconds=3),
        T0 + timedelta(seconds=7),
        T0 + timedelta(seconds=15),
    ]
    outbox.refresh_from_db()
    assert outbox.attempts == 4
    assert outbox.status == "pending"

    services.process_outbox_message(outbox.pk, now=current)
    outbox.refresh_from_db()
    assert outbox.attempts == 5
    assert outbox.status == "failed"
    assert FakeExternalMessage.objects.count() == 0
    assert Receipt.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_spec_permanent_error_stops_immediately() -> None:
    fake_service.set_fake_mode("permanent_error")
    outbox = _create_pending("pay-permanent")

    services.process_outbox_message(outbox.pk, now=T0)
    outbox.refresh_from_db()
    assert outbox.status == "failed"
    assert outbox.attempts == 1
    assert "permanent" in outbox.last_error.lower()

    services.process_outbox_message(outbox.pk, now=T0 + timedelta(days=1))
    outbox.refresh_from_db()
    assert outbox.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_spec_operator_retry_dispatches_failed_dispatch() -> None:
    fake_service.set_fake_mode("permanent_error")
    outbox = _create_pending("pay-retry")
    services.process_outbox_message(outbox.pk, now=T0)

    fake_service.set_fake_mode("ok")
    call_command("retry_receipt_dispatch", str(outbox.pk))

    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert Receipt.objects.count() == 1
    assert FakeExternalMessage.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_timeout_after_accept_gives_one_external_message_and_one_receipt() -> None:
    """The real Fake records the message, then times out; lookup must find it."""
    fake_service.set_fake_mode("accept_then_timeout")
    with monkeypatch_delay():
        services.record_payment(reference="pay-timeout", amount_rial=900, now=T0)

    outbox = OutboxMessage.objects.get()
    assert outbox.status == "pending"

    assert services.process_outbox_message(outbox.pk, now=T0) == "sent"

    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert outbox.attempts == 1
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_crash_between_sent_and_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    outbox = _create_pending("pay-crash-boundary")

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("worker crashed after send")

    with monkeypatch.context() as patch:
        patch.setattr(services, "record_receipt", crash)
        with pytest.raises(RuntimeError, match="worker crashed"):
            services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert outbox.status == "in_progress"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 0

    from receipts.services import LEASE_SECONDS

    # The dispatch holds a lease; recovery starts only once it expires.
    services.sweep_outbox(now=T0 + timedelta(seconds=LEASE_SECONDS))
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(15)
def test_spec_two_workers_one_payment() -> None:
    outbox = _create_pending("pay-two-workers")
    barrier = threading.Barrier(2)

    def work() -> None:
        barrier.wait(timeout=10)
        try:
            services.process_outbox_message(outbox.pk, now=T0)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(work) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)

    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "mode", ["ok", "temporary_error", "permanent_error", "accept_then_timeout"]
)
def test_spec_fake_worker_contract_modes(mode: str) -> None:
    fake_service.set_fake_mode(mode)
    service = fake_service.FakeReceiptService()
    key = "receipt:contract"

    if mode == "ok":
        first = service.send(key, {"n": 1})
        second = service.send(key, {"n": 1})
        assert first.external_message_id == second.external_message_id
        assert FakeExternalMessage.objects.count() == 1
    elif mode == "temporary_error":
        with pytest.raises(fake_service.TemporaryReceiptError):
            service.send(key, {"n": 1})
        assert FakeExternalMessage.objects.count() == 0
    elif mode == "permanent_error":
        with pytest.raises(fake_service.PermanentReceiptError):
            service.send(key, {"n": 1})
        assert FakeExternalMessage.objects.count() == 0
    else:
        with pytest.raises(fake_service.ReceiptTimeoutError):
            service.send(key, {"n": 1})
        assert FakeExternalMessage.objects.count() == 1
        assert service.lookup(key) is not None
        assert service.send(key, {"n": 1}).external_message_id
        assert FakeExternalMessage.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_failed_attempts_observable() -> None:
    fake_service.set_fake_mode("temporary_error")
    outbox = _create_pending("pay-observe")
    services.process_outbox_message(outbox.pk, now=T0)

    state = OutboxMessage.objects.values("status", "attempts", "last_error", "next_attempt_at").get(
        pk=outbox.pk
    )
    assert state["status"] == "pending"
    assert state["attempts"] == 1
    assert "temporary" in state["last_error"].lower()
    assert state["next_attempt_at"] == T0 + timedelta(seconds=1)


def test_spec_redis_broker_and_postgres_durable_state() -> None:
    database = settings.DATABASES["default"]
    assert database["ENGINE"] == "django.db.backends.postgresql"
    # pytest-django rewrites NAME to test_task08 for the isolated test database.
    assert database["NAME"] in ("task08", "test_task08")
    assert database["HOST"] == os.environ.get("POSTGRES_HOST", "localhost")
    assert database["PORT"] == os.environ.get("POSTGRES_PORT", "5432")
    assert connection.vendor == "postgresql"
    assert (
        f"redis://{os.environ.get('REDIS_HOST', '127.0.0.1')}:"
        f"{os.environ.get('REDIS_PORT', '6379')}/8"
    ) == settings.CELERY_BROKER_URL
    assert settings.CELERY_BEAT_SCHEDULE["sweep-pending-receipts"]["task"] == (
        "receipts.tasks.sweep_outbox"
    )
    assert app.main == "task08"


@pytest.mark.django_db(transaction=True)
def test_spec_money_integer_rial_and_utc_timestamps() -> None:
    payment = services.record_payment(reference="pay-money", amount_rial=Decimal("12345"), now=T0)
    assert isinstance(payment.amount_rial, int)
    assert timezone.is_aware(payment.created_at)
    assert payment.created_at.utcoffset() == timedelta(0)


@pytest.mark.django_db(transaction=True)
def test_spec_real_migration_creates_tables() -> None:
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(connection)
    assert "receipts" not in settings.MIGRATION_MODULES
    assert ("receipts", "0001_initial") in loader.disk_migrations
    assert ("receipts", "0001_initial") in loader.applied_migrations
    assert ("receipts", "0002_outboxattempt") in loader.disk_migrations
    assert ("receipts", "0002_outboxattempt") in loader.applied_migrations
    for table in (
        "receipts_payment",
        "receipts_outboxmessage",
        "receipts_fakeexternalmessage",
        "receipts_receipt",
        "receipts_outboxattempt",
    ):
        assert table in connection.introspection.table_names()


def test_spec_ensure_database_is_idempotent_and_exposed_as_command() -> None:
    from io import StringIO

    from db_utils import ensure_database

    ensure_database()
    ensure_database()
    output = StringIO()
    call_command("ensure_db", stdout=output)
    assert "task08" in output.getvalue()


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(30)
def test_spec_slow_dispatch_does_not_consume_attempts() -> None:
    from receipts.services import LEASE_SECONDS

    outbox = _create_pending("pay-slow-dispatch")
    started = threading.Event()
    release = threading.Event()

    class SlowService(fake_service.FakeReceiptService):
        def send(self, key: str, payload: dict) -> fake_service.SendResult:
            started.set()
            assert release.wait(timeout=15)
            return super().send(key, payload)

    def work() -> None:
        try:
            services.process_outbox_message(outbox.pk, now=T0, service=SlowService())
        finally:
            connection.close()

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    assert started.wait(timeout=10)

    outbox.refresh_from_db()
    assert outbox.next_attempt_at == T0 + timedelta(seconds=LEASE_SECONDS)

    # Beat re-runs every 5 s; none of these ticks may re-claim a leased row.
    for step in range(1, 6):
        services.sweep_outbox(now=T0 + timedelta(seconds=5 * step))

    release.set()
    worker.join(timeout=10)
    assert not worker.is_alive()

    outbox.refresh_from_db()
    assert outbox.attempts == 1
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_reclaim_increments_attempts_after_crash() -> None:
    """Round 2: a crashed worker's re-claim is a real attempt (was deliberately changed)."""
    from receipts.services import LEASE_SECONDS

    outbox = _create_pending("pay-reclaim")
    OutboxMessage.objects.filter(pk=outbox.pk).update(
        status=OutboxMessage.Status.IN_PROGRESS,
        attempts=1,
        next_attempt_at=T0,
    )

    # The lease expired (crashed worker), so the row is due again.
    assert services.claim_due_messages(now=T0) == [outbox.pk]
    services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert outbox.attempts == 2
    assert outbox.next_attempt_at == T0 + timedelta(seconds=LEASE_SECONDS)


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(30)
def test_spec_two_workers_never_process_same_message() -> None:
    from receipts.services import LEASE_SECONDS

    outbox = _create_pending("pay-two-worker-lease")
    barrier = threading.Barrier(2)
    started = threading.Event()
    release = threading.Event()
    done = [threading.Event() for _ in range(2)]
    first_worker: list[int] = []
    send_count: list[str] = []
    count_lock = threading.Lock()

    def make_service(worker_id: int) -> fake_service.FakeReceiptService:
        class CountingService(fake_service.FakeReceiptService):
            def send(self, key: str, payload: dict) -> fake_service.SendResult:
                with count_lock:
                    send_count.append(key)
                    is_first = len(send_count) == 1
                    if is_first:
                        first_worker.append(worker_id)
                if is_first:
                    started.set()
                    assert release.wait(timeout=15)
                return super().send(key, payload)

        return CountingService()

    def work(worker_id: int) -> None:
        barrier.wait(timeout=10)
        try:
            services.process_outbox_message(outbox.pk, now=T0, service=make_service(worker_id))
        finally:
            done[worker_id].set()
            connection.close()

    threads = [threading.Thread(target=work, args=(i,), daemon=True) for i in range(2)]
    for thread in threads:
        thread.start()

    assert started.wait(timeout=10)
    assert len(first_worker) == 1
    assert done[1 - first_worker[0]].wait(timeout=10)
    release.set()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    outbox.refresh_from_db()
    assert outbox.attempts == 1
    assert outbox.next_attempt_at == T0 + timedelta(seconds=LEASE_SECONDS)
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1
    assert len(send_count) == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(30)
def test_spec_fake_service_concurrent_send_creates_one_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers = 12
    barrier = threading.Barrier(workers)
    results: list[str] = []
    errors: list[Exception] = []

    def work() -> None:
        try:
            barrier.wait(timeout=10)
            result = fake_service.FakeReceiptService().send("receipt:race", {"n": 1})
            results.append(result.external_message_id)
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=work, daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert errors == []
    assert len(results) == workers
    assert len(set(results)) == 1
    assert FakeExternalMessage.objects.filter(idempotency_key="receipt:race").count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("bad_amount", [12.5, "12000", Decimal("12.5"), None, True])
def test_spec_rejects_float_and_non_integer_amounts(bad_amount: object) -> None:
    with pytest.raises(ValueError, match="amount_rial"):
        services.record_payment(reference="pay-bad-amount", amount_rial=bad_amount, now=T0)

    assert Payment.objects.count() == 0
    assert OutboxMessage.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_spec_operator_retry_requires_failed_state() -> None:
    from django.core.management.base import CommandError

    pending = _create_pending("pay-retry-pending")
    with pytest.raises(CommandError, match="only failed"):
        call_command("retry_receipt_dispatch", str(pending.pk))

    pending.refresh_from_db()
    assert pending.status == "pending"
    assert pending.attempts == 0
    assert FakeExternalMessage.objects.count() == 0

    payment = services.record_payment(reference="pay-retry-sent", amount_rial=100, now=T0)
    sent = OutboxMessage.objects.get(payment=payment)
    with pytest.raises(CommandError, match="only failed"):
        call_command("retry_receipt_dispatch", str(sent.pk))

    assert FakeExternalMessage.objects.count() == 1
