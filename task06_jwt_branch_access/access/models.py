"""Database schema for branches, memberships, invoices and login sessions."""

import uuid

from django.conf import settings
from django.db import models

from access.clocks import utcnow


class Branch(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    ROLE_ANALYST = "analyst"
    ROLE_CUSTOMER = "customer"
    ROLE_CHOICES = [(ROLE_ANALYST, "Analyst"), (ROLE_CUSTOMER, "Customer")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "branch", "role"], name="uniq_user_branch_role")
        ]


class Invoice(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="invoices")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="own_invoices",
    )
    number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(default=utcnow)


class LoginSession(models.Model):
    """One login = one session; refresh rotation and logout act on this row."""

    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_sessions"
    )
    refresh_jti = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=utcnow)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None
