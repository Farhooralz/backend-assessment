"""Persistent model for a fixed-capacity class and its reservations."""

from django.db import models


class GymClass(models.Model):
    """A class with a fixed number of seats and no overbooking allowed."""

    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()

    def __str__(self) -> str:
        """Return a readable label for test output and admin pages."""
        return f"{self.name} ({self.capacity} seats)"


class Reservation(models.Model):
    """One user's seat for one class, identified by a user-scoped idempotency key."""

    gym_class = models.ForeignKey(
        GymClass,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    user_id = models.PositiveBigIntegerField()
    key = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "gym_class"],
                name="uniq_reservation_user_class",
            ),
            models.UniqueConstraint(
                fields=["user_id", "key"],
                name="uniq_reservation_user_key",
            ),
        ]
