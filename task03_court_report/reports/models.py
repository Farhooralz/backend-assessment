"""Domain models for the per-court financial report."""

from django.db import models


class Branch(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self) -> str:
        return self.name


class Court(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="courts")
    name = models.CharField(max_length=200)

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self) -> str:
        return self.name


class Booking(models.Model):
    court = models.ForeignKey(Court, on_delete=models.CASCADE, related_name="bookings")
    tags = models.ManyToManyField(Tag, related_name="bookings")
    start_date = models.DateField()
    confirmed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["court", "start_date"], name="booking_court_start_idx"),
            models.Index(fields=["start_date"], name="booking_start_idx"),
        ]


class Payment(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    successful = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_amount_positive",
                violation_error_message="Payment amount must be positive.",
            )
        ]
        indexes = [
            models.Index(fields=["booking", "successful"], name="payment_booking_success_idx")
        ]
