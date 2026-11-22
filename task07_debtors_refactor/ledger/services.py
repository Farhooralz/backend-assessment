"""Debtors report service: issued invoices, authorized branch, positive debt only."""

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from ledger.models import Invoice, Membership, Payment

ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


def debtors(user: object, branch_id: int) -> list[dict[str, int | Decimal]]:
    """Return ``[{"id": pk, "due": Decimal}]`` in ascending id order.

    Authorization is checked against a live active Membership, and the amount is
    aggregated in SQL so a report over hundreds of invoices costs two queries.
    """
    user_id = getattr(user, "id", user)
    authorized = Membership.objects.filter(
        user_id=user_id, branch_id=branch_id, is_active=True
    ).exists()
    if not authorized:
        return []

    settled_total = Coalesce(
        Sum("payments__amount", filter=Q(payments__status=Payment.Status.SETTLED)),
        Value(ZERO, output_field=MONEY_FIELD),
    )
    due = ExpressionWrapper(F("total") - settled_total, output_field=MONEY_FIELD)
    rows = (
        Invoice.objects.filter(branch_id=branch_id, status=Invoice.Status.ISSUED)
        .annotate(due=due)
        .filter(due__gt=ZERO)
        .order_by("id")
        .values_list("id", "due")
    )
    return [{"id": pk, "due": amount} for pk, amount in rows]
