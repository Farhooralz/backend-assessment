"""Minimal ledger schema: invoices, their payments, and branch memberships."""

from django.db import models


class Invoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        DRAFT = "draft", "Draft"
        SETTLED = "settled", "Settled"
        CANCELLED = "cancelled", "Cancelled"

    branch_id = models.IntegerField()
    total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices)


class Payment(models.Model):
    class Status(models.TextChoices):
        SETTLED = "settled", "Settled"
        PENDING = "pending", "Pending"
        FAILED = "failed", "Failed"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices)


class Membership(models.Model):
    user_id = models.IntegerField()
    branch_id = models.IntegerField()
    is_active = models.BooleanField(default=True)
