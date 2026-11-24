"""Small models that carry just enough state for the cancel scenario."""

from django.db import models


class Branch(models.Model):
    """Organisational unit that scopes manager permissions."""

    name = models.CharField(max_length=100)


class User(models.Model):
    """A participant; ``is_manager`` plus ``branch`` decide permission."""

    name = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    is_manager = models.BooleanField(default=False)


class Reservation(models.Model):
    """A confirmed-or-cancelled booking paid for in whole rials."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reservations")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    start = models.DateTimeField()
    payment_amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="confirmed")


class RefundDocument(models.Model):
    """One refund record per cancelled reservation."""

    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE)
    amount = models.PositiveIntegerField()
