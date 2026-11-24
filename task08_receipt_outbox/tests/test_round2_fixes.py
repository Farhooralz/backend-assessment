"""Round-2 regression tests: each finding must be red before its fix."""

import os
import threading
import time
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import psycopg
import pytest
import redis
from celery.contrib.testing.worker import start_worker
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from celery_app import app
from db_utils import pg_params
from receipts import fake_service, services
from receipts.models import FakeExternalMessage, OutboxMessage, Receipt
from receipts.tasks import dispatch_receipt

T0 = timezone.make_aware(datetime(2026, 2, 1, 9, 0, 0), UTC)
LEASE = services.LEASE_SECONDS


def _pending(reference: str) -> OutboxMessage:
    """Create a committed outbox row without publishing it."""
    with patch.object(dispatch_receipt, "delay", lambda *args, **kwargs: None):
        services.record_payment(reference=reference, amount_rial=1000, now=T0)
    return OutboxMessage.objects.get(payment__reference=reference)


def _count_sends(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Count calls to the Fake's send, without changing its behaviour."""
    calls: list[str] = []
    original = fake_service.FakeReceiptService.send

    def counting(self: fake_service.FakeReceiptService, key: str, payload: dict) -> object:
        calls.append(key)
        return original(self, key, payload)

    monkeypatch.setattr(fake_service.FakeReceiptService, "send", counting)
    return calls


# --- Finding 1: backoff bypass ------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_spec_pending_row_with_future_next_attempt_is_not_processed_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outbox = _pending("r2-early")
    OutboxMessage.objects.filter(pk=outbox.pk).update(next_attempt_at=T0 + timedelta(seconds=10))
    sends = _count_sends(monkeypatch)

    status = services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert status == "pending"
    assert outbox.status == "pending"
    assert outbox.attempts == 0
    assert sends == []
    assert FakeExternalMessage.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_spec_duplicate_sweep_enqueues_send_once(monkeypatch: pytest.MonkeyPatch) -> None:
    outbox = _pending("r2-duplicate-sweep")
    enqueued: list[int] = []
    with patch.object(dispatch_receipt, "delay", lambda message_id: enqueued.append(message_id)):
        assert services.sweep_outbox(now=T0) == 1
        assert services.sweep_outbox(now=T0) == 1
    assert enqueued == [outbox.pk, outbox.pk]

    sends = _count_sends(monkeypatch)
    for message_id in enqueued:
        assert services.process_outbox_message(message_id, now=T0) == "sent"

    outbox.refresh_from_db()
    assert len(sends) == 1
    assert outbox.attempts == 1
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_spec_duplicate_task_after_temporary_failure_does_not_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service.set_fake_mode("temporary_error")
    outbox = _pending("r2-duplicate-temporary")
    sends = _count_sends(monkeypatch)

    first = services.process_outbox_message(outbox.pk, now=T0)
    second = services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert first == second == "pending"
    assert outbox.attempts == 1
    assert len(sends) == 1
    assert FakeExternalMessage.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("offset", "should_send"),
    [
        (timedelta(0), True),
        (timedelta(microseconds=1), False),
    ],
)
def test_spec_next_attempt_at_boundary_is_inclusive(
    monkeypatch: pytest.MonkeyPatch, offset: timedelta, should_send: bool
) -> None:
    outbox = _pending(f"r2-boundary-{should_send}")
    OutboxMessage.objects.filter(pk=outbox.pk).update(next_attempt_at=T0 + offset)
    sends = _count_sends(monkeypatch)

    services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert bool(sends) is should_send
    assert outbox.attempts == (1 if should_send else 0)


# --- Finding 2: stale worker must not overwrite state -------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(30)
def test_spec_stale_worker_defer_cannot_overwrite_sent() -> None:
    outbox = _pending("r2-stale-defer")
    started = threading.Event()
    release = threading.Event()
    errors: list[Exception] = []

    class SlowFail(fake_service.FakeReceiptService):
        def send(self, key: str, payload: dict) -> fake_service.SendResult:
            started.set()
            assert release.wait(timeout=15)
            raise fake_service.TemporaryReceiptError("late failure")

    def worker_a() -> None:
        try:
            services.process_outbox_message(outbox.pk, now=T0, service=SlowFail())
        except Exception as exc:  # collected so the main thread can assert it
            errors.append(exc)
        finally:
            connection.close()

    thread = threading.Thread(target=worker_a, daemon=True)
    thread.start()
    assert started.wait(timeout=15)

    # A's lease was T0 + LEASE; at that instant worker B may take over and finish.
    assert services.process_outbox_message(outbox.pk, now=T0 + timedelta(seconds=LEASE)) == "sent"
    outbox.refresh_from_db()
    assert outbox.status == "sent"

    release.set()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert errors == []

    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert outbox.attempts == 2
    assert "late failure" not in outbox.last_error


@pytest.mark.django_db(transaction=True)
def test_spec_receipt_and_sent_write_roll_back_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outbox = _pending("r2-atomic-sent")
    original_save = OutboxMessage.save

    def failing_save(self: OutboxMessage, *args: object, **kwargs: object) -> None:
        if self.pk == outbox.pk and self.status == "sent":
            raise RuntimeError("crash after receipt")
        original_save(self, *args, **kwargs)

    monkeypatch.setattr(OutboxMessage, "save", failing_save)
    with pytest.raises(RuntimeError, match="crash after receipt"):
        services.process_outbox_message(outbox.pk, now=T0)

    # A separate connection proves the receipt was rolled back, not just hidden.
    params = pg_params(settings.DATABASES["default"]["NAME"])
    with psycopg.connect(**params) as conn:
        receipts = conn.execute("SELECT count(*) FROM receipts_receipt").fetchone()[0]
        status = conn.execute(
            "SELECT status FROM receipts_outboxmessage WHERE id = %s", (outbox.pk,)
        ).fetchone()[0]
    assert receipts == 0
    assert status == "in_progress"

    attempt_model = apps.get_model("receipts", "OutboxAttempt")
    assert attempt_model.objects.filter(message_id=outbox.pk).count() == 1


# --- Finding 3: crash loop cap ------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_spec_crash_reclaim_beyond_max_attempts_fails() -> None:
    outbox = _pending("r2-crash-cap")
    OutboxMessage.objects.filter(pk=outbox.pk).update(
        status=OutboxMessage.Status.IN_PROGRESS,
        attempts=services.MAX_ATTEMPTS,
        next_attempt_at=T0,
    )

    status = services.process_outbox_message(outbox.pk, now=T0)

    outbox.refresh_from_db()
    assert status == "failed"
    assert outbox.status == "failed"
    assert outbox.last_error == "worker crashed repeatedly"
    assert FakeExternalMessage.objects.count() == 0
    assert Receipt.objects.count() == 0


# --- Finding 4: sweeper claims are not exclusive ------------------------------


@pytest.mark.django_db(transaction=True)
def test_spec_claim_due_messages_does_not_write_state() -> None:
    outbox = _pending("r2-claim-read-only")

    assert services.claim_due_messages(now=T0) == [outbox.pk]

    outbox.refresh_from_db()
    assert outbox.status == "pending"
    assert outbox.attempts == 0
    assert outbox.next_attempt_at == T0


# --- Finding 5: operator retry uses the safe enqueue helper -------------------


@pytest.mark.django_db(transaction=True)
def test_spec_operator_retry_broker_down_leaves_pending_for_sweeper(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(timezone, "now", lambda: T0)
    fake_service.set_fake_mode("permanent_error")
    outbox = _pending("r2-retry-broker-down")
    services.process_outbox_message(outbox.pk, now=T0)
    outbox.refresh_from_db()
    assert outbox.status == "failed"

    with patch.object(
        dispatch_receipt, "delay", side_effect=redis.exceptions.ConnectionError("broker down")
    ):
        call_command("retry_receipt_dispatch", str(outbox.pk))

    outbox.refresh_from_db()
    assert outbox.status == "pending"
    assert outbox.attempts == 0
    assert "broker down" in caplog.text

    fake_service.set_fake_mode("ok")
    services.sweep_outbox(now=T0)
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert Receipt.objects.count() == 1


# --- Finding 6: spec sample, lookup NOT patched --------------------------------


@pytest.mark.django_db(transaction=True)
def test_spec_timeout_with_missing_lookup_retry_resends_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service.set_fake_mode("accept_then_timeout")
    outbox = _pending("r2-timeout-missing-lookup")
    monkeypatch.setattr(fake_service.FakeReceiptService, "lookup", lambda self, key: None)

    assert services.process_outbox_message(outbox.pk, now=T0) == "pending"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 0

    fake_service.set_fake_mode("ok")
    assert services.process_outbox_message(outbox.pk, now=T0 + timedelta(seconds=1)) == "sent"
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


# --- Finding 7: one clock for sweep and task ----------------------------------


@pytest.mark.django_db(transaction=True)
def test_spec_frozen_clock_drives_sweep_and_task_lease_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moment = T0
    monkeypatch.setattr(timezone, "now", lambda: moment)
    payment = services.record_payment(reference="r2-frozen", amount_rial=1000, now=T0)
    OutboxMessage.objects.filter(payment=payment).update(next_attempt_at=T0 + timedelta(days=1))
    outbox = OutboxMessage.objects.create(
        payment=payment,
        idempotency_key="receipt:r2-frozen-lease",
        payload={"reference": "r2-frozen"},
        status=OutboxMessage.Status.IN_PROGRESS,
        attempts=1,
        next_attempt_at=T0,
    )

    assert services.sweep_outbox() == 1
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert outbox.attempts == 2
    assert outbox.next_attempt_at == T0 + timedelta(seconds=LEASE)


# --- Finding 8: real Redis broker ---------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(90)
def test_spec_real_redis_broker_worker_marks_row_sent(settings: object) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    app.conf.task_always_eager = False
    app.conf.task_eager_propagates = False

    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "127.0.0.1"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=8,
    )
    queue = app.conf.task_default_queue or "celery"
    client.delete(queue)
    outbox = _pending("r2-real-redis")

    dispatch_receipt.delay(outbox.pk)
    assert client.llen(queue) >= 1

    with start_worker(app, perform_ping_check=False, shutdown_timeout=15):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            outbox.refresh_from_db()
            if outbox.status == "sent":
                break
            time.sleep(0.1)

    client.delete(queue)
    outbox.refresh_from_db()
    assert outbox.status == "sent"
    assert outbox.attempts == 1
    assert FakeExternalMessage.objects.count() == 1
    assert Receipt.objects.count() == 1


# --- Finding 9: per-attempt observability -------------------------------------


@pytest.mark.django_db(transaction=True)
def test_spec_attempt_history_records_one_row_per_attempt() -> None:
    attempt_model = apps.get_model("receipts", "OutboxAttempt")
    fake_service.set_fake_mode("temporary_error")
    outbox = _pending("r2-attempt-history")

    services.process_outbox_message(outbox.pk, now=T0)
    services.process_outbox_message(outbox.pk, now=T0 + timedelta(seconds=1))

    rows = list(
        attempt_model.objects.filter(message=outbox)
        .order_by("attempt_no")
        .values("attempt_no", "outcome", "error", "started_at")
    )
    assert [row["attempt_no"] for row in rows] == [1, 2]
    assert [row["outcome"] for row in rows] == ["deferred", "deferred"]
    assert "temporary" in rows[0]["error"]
    assert rows[0]["started_at"] == T0
    assert rows[1]["started_at"] == T0 + timedelta(seconds=1)


@pytest.mark.django_db(transaction=True)
def test_spec_operator_command_prints_attempt_history() -> None:
    apps.get_model("receipts", "OutboxAttempt")
    fake_service.set_fake_mode("permanent_error")
    outbox = _pending("r2-history-command")
    services.process_outbox_message(outbox.pk, now=T0)

    output = StringIO()
    with patch.object(dispatch_receipt, "delay", lambda *args, **kwargs: None):
        call_command("retry_receipt_dispatch", str(outbox.pk), stdout=output)

    text = output.getvalue()
    assert "attempt 1" in text
    assert "failed" in text
