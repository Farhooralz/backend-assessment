"""Spec-driven tests for the recoverable receipt dispatch (Task 8)."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
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
def test_spec_broker_crash_after_commit_keeps_receipt() -> None:
    with monkeypatch_delay():
        services.record_payment(reference="pay-broker-crash", amount_rial=700, now=T0)

    outbox = OutboxMessage.objects.get()
    assert outbox.status == "pending"
    assert FakeExternalMessage.objects.count() == 0

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
def test_spec_select_for_update_skip_locked_claiming() -> None:
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
def test_spec_timeout_after_accept_gives_one_external_message_and_one_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service.set_fake_mode("accept_then_timeout")
    with monkeypatch_delay():
        services.record_payment(reference="pay-timeout", amount_rial=900, now=T0)

    outbox = OutboxMessage.objects.get()
    assert outbox.status == "pending"

    with monkeypatch.context() as patch:
        patch.setattr(fake_service.FakeReceiptService, "lookup", lambda self, key: None)
        services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert outbox.status == "pending"
    assert outbox.attempts == 1
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 0

    fake_service.set_fake_mode("ok")
    services.sweep_outbox(now=T0 + timedelta(seconds=1))

    outbox.refresh_from_db()
    assert outbox.status == "sent"
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

    services.sweep_outbox(now=T0)
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(15)
def test_spec_two_workers_one_payment() -> None:
    outbox = _create_pending("pay-two-workers")

    def work() -> None:
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
