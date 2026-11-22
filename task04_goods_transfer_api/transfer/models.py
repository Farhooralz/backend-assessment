"""Persistence model of the goods transfer request cycle."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class Staff(models.Model):
    """A user's branch and role; used for both visibility and action rights."""

    class Role(models.TextChoices):
        EMPLOYEE = "employee", "Destination employee"
        SOURCE_MANAGER = "source_manager", "Source manager"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role} @ {self.branch})"


class TransferRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    source = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="outgoing_transfers")
    destination = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="incoming_transfers"
    )
    item_name = models.CharField(max_length=200)
    quantity = models.IntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_transfers"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="decided_transfers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="transfer_quantity_positive"),
            models.CheckConstraint(
                condition=~Q(source=F("destination")), name="transfer_distinct_branches"
            ),
        ]

    def __str__(self) -> str:
        route = f"{self.source}->{self.destination}"
        return f"{self.item_name} x{self.quantity} {route} ({self.status})"
