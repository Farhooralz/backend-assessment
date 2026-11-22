"""Plain services for the transactional outbox and its recovery rules."""

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from receipts import fake_service
from receipts.models import OutboxMessage, Payment, Receipt

MAX_ATTEMPTS = 5


def backoff_seconds(attempts: int) -> int:
    """Return increasing retry intervals: 1, 2, 4, 8 seconds."""
    return 2 ** (attempts - 1)


def _enqueue(message_id: int) -> None:
    from receipts.tasks import dispatch_receipt

    dispatch_receipt.delay(message_id)


def record_payment(reference: str, amount_rial: int, *, now: datetime | None = None) -> Payment:
    """Store the payment and its receipt outbox row in one transaction."""
    moment = now or timezone.now()
    rial = int(amount_rial)
    with transaction.atomic():
        payment = Payment.objects.create(reference=reference, amount_rial=rial)
        outbox = OutboxMessage.objects.create(
            payment=payment,
            idempotency_key=f"receipt:{reference}",
            payload={"reference": reference, "amount_rial": rial},
            next_attempt_at=moment,
        )
        transaction.on_commit(lambda: _enqueue(outbox.pk))
    return payment


def claim_due_messages(*, now: datetime | None = None) -> list[int]:
    """Claim due rows with skip_locked so two workers never take the same row."""
    moment = now or timezone.now()
    with transaction.atomic():
        ids = list(
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=(OutboxMessage.Status.PENDING, OutboxMessage.Status.IN_PROGRESS),
                next_attempt_at__lte=moment,
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if ids:
            OutboxMessage.objects.filter(pk__in=ids).update(status=OutboxMessage.Status.IN_PROGRESS)
    return ids


def sweep_outbox(*, now: datetime | None = None) -> int:
    """Periodic recovery: enqueue every due row, including rows left by a crash."""
    ids = claim_due_messages(now=now)
    for message_id in ids:
        _enqueue(message_id)
    return len(ids)


def record_receipt(outbox: OutboxMessage, external_message_id: str) -> None:
    """Create at most one local receipt for an outbox row."""
    with transaction.atomic():
        Receipt.objects.get_or_create(
            outbox=outbox,
            defaults={
                "idempotency_key": outbox.idempotency_key,
                "external_message_id": external_message_id,
            },
        )


def process_outbox_message(
    message_id: int,
    *,
    now: datetime | None = None,
    service: fake_service.FakeReceiptService | None = None,
) -> str:
    """Dispatch one outbox row; idempotency makes repeated attempts safe."""
    moment = now or timezone.now()
    gateway = service or fake_service.FakeReceiptService()
    with transaction.atomic():
        outbox = OutboxMessage.objects.select_for_update().get(pk=message_id)
        if outbox.status in (OutboxMessage.Status.SENT, OutboxMessage.Status.FAILED):
            return outbox.status
        attempts = outbox.attempts + 1
        outbox.status = OutboxMessage.Status.IN_PROGRESS
        outbox.attempts = attempts
        outbox.save(update_fields=["status", "attempts"])

    try:
        result = gateway.send(outbox.idempotency_key, outbox.payload)
    except fake_service.ReceiptTimeoutError:
        result = gateway.lookup(outbox.idempotency_key)
        if result is None:
            return _defer(outbox, attempts, moment, "temporary: response timed out")
    except fake_service.PermanentReceiptError as exc:
        return _fail(outbox, str(exc))
    except fake_service.TemporaryReceiptError as exc:
        return _defer(outbox, attempts, moment, f"temporary: {exc}")

    record_receipt(outbox, result.external_message_id)
    with transaction.atomic():
        outbox.status = OutboxMessage.Status.SENT
        outbox.last_error = ""
        outbox.save(update_fields=["status", "last_error"])
    return OutboxMessage.Status.SENT


def _defer(outbox: OutboxMessage, attempts: int, now: datetime, error: str) -> str:
    """Schedule another attempt, or stop after the fifth failure."""
    exhausted = attempts >= MAX_ATTEMPTS
    next_attempt = now if exhausted else now + timedelta(seconds=backoff_seconds(attempts))
    with transaction.atomic():
        outbox.status = OutboxMessage.Status.FAILED if exhausted else OutboxMessage.Status.PENDING
        outbox.next_attempt_at = next_attempt
        outbox.last_error = error
        outbox.save(update_fields=["status", "next_attempt_at", "last_error"])
    return outbox.status


def _fail(outbox: OutboxMessage, error: str) -> str:
    """Stop immediately for a permanent rejection."""
    with transaction.atomic():
        outbox.status = OutboxMessage.Status.FAILED
        outbox.last_error = f"permanent: {error}"
        outbox.save(update_fields=["status", "last_error"])
    return OutboxMessage.Status.FAILED
