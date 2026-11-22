"""Durable state for payments, outbox rows, the fake external service and receipts."""

from django.db import models
from django.utils import timezone


class Payment(models.Model):
    reference = models.CharField(max_length=100, unique=True)
    amount_rial = models.BigIntegerField()
    created_at = models.DateTimeField(default=timezone.now)


class OutboxMessage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        SENT = "sent"
        FAILED = "failed"

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="outbox_messages")
    idempotency_key = models.CharField(max_length=200, unique=True)
    payload = models.JSONField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class OutboxAttempt(models.Model):
    """One durable record per dispatch attempt, including crashed in-flight ones."""

    class Outcome(models.TextChoices):
        IN_PROGRESS = "in_progress"
        SENT = "sent"
        DEFERRED = "deferred"
        FAILED = "failed"

    message = models.ForeignKey(
        OutboxMessage, on_delete=models.CASCADE, related_name="attempts_history"
    )
    attempt_no = models.PositiveIntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.IN_PROGRESS)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "attempt_no"], name="receipts_one_row_per_attempt"
            )
        ]


class FakeExternalMessage(models.Model):
    """Stands in for the external service's own durable, keyed message store."""

    idempotency_key = models.CharField(max_length=200, unique=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)


class Receipt(models.Model):
    outbox = models.OneToOneField(OutboxMessage, on_delete=models.CASCADE, related_name="receipt")
    idempotency_key = models.CharField(max_length=200, unique=True)
    external_message_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
