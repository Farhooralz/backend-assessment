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
