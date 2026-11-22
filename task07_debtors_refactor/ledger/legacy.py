"""The verbatim function under review, kept only for regression tests."""

from ledger.models import Invoice


def debtors(user, branch_id):
    rows = []
    for inv in Invoice.objects.filter(branch_id=branch_id):
        paid = sum(p.amount for p in inv.payments.all())
        if inv.total != paid:
            rows.append({"id": inv.pk, "due": inv.total - paid})
    return rows
