"""Contract, regression, and defect tests for the debtors report."""

import inspect
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledger import legacy, services
from ledger.models import Invoice, Membership, Payment

BRANCH_ID = 7
OTHER_BRANCH_ID = 99


def grant(user: object, branch_id: int = BRANCH_ID, *, active: bool = True) -> Membership:
    return Membership.objects.create(
        user_id=user.id,
        branch_id=branch_id,
        is_active=active,  # type: ignore[attr-defined]
    )


def invoice(
    *,
    pk: int | None = None,
    total: str = "300",
    branch_id: int = BRANCH_ID,
    status: str = Invoice.Status.ISSUED,
) -> Invoice:
    values = {"branch_id": branch_id, "total": Decimal(total), "status": status}
    if pk is not None:
        values["id"] = pk
    return Invoice.objects.create(**values)


def payment(inv: Invoice, amount: str, status: str = Payment.Status.SETTLED) -> Payment:
    return Payment.objects.create(invoice=inv, amount=Decimal(amount), status=status)


@pytest.mark.django_db
def test_spec_signature_and_output_keys_preserved(user: object) -> None:
    assert list(inspect.signature(services.debtors).parameters) == ["user", "branch_id"]
    grant(user)
    inv = invoice()
    rows = services.debtors(user, BRANCH_ID)
    assert len(rows) == 1
    assert set(rows[0]) == {"id", "due"}
    assert rows[0]["id"] == inv.pk


@pytest.mark.django_db
def test_spec_regression_legacy_positive_debt_and_keys(user: object) -> None:
    """Characterization: the old code was right for a plain issued invoice."""
    inv = invoice(total="300")
    payment(inv, "100")
    assert legacy.debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("200.00")}]


@pytest.mark.django_db
def test_spec_regression_legacy_zero_debt_is_skipped(user: object) -> None:
    inv = invoice(total="100")
    payment(inv, "100")
    assert legacy.debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
def test_spec_money_is_decimal(user: object) -> None:
    grant(user)
    inv = invoice(total="300.50")
    payment(inv, "100.25")
    due = services.debtors(user, BRANCH_ID)[0]["due"]
    assert isinstance(due, Decimal)
    assert not isinstance(due, float)


@pytest.mark.django_db
def test_spec_sample_invoice_300_due_180(user: object) -> None:
    grant(user)
    inv = invoice(pk=300, total="300")
    payment(inv, "120", Payment.Status.SETTLED)
    payment(inv, "100", Payment.Status.PENDING)
    assert services.debtors(user, BRANCH_ID) == [{"id": 300, "due": Decimal("180.00")}]


@pytest.mark.django_db
def test_spec_acceptance_status_and_other_branch_excluded(user: object) -> None:
    grant(user)
    good = invoice(total="300")
    for status in (Invoice.Status.DRAFT, Invoice.Status.SETTLED, Invoice.Status.CANCELLED):
        invoice(total="300", status=status)
    invoice(total="300", branch_id=OTHER_BRANCH_ID)
    assert services.debtors(user, BRANCH_ID) == [{"id": good.pk, "due": Decimal("300.00")}]


@pytest.mark.django_db
def test_spec_defect_1_only_issued_invoices(user: object) -> None:
    grant(user)
    issued = invoice(total="50")
    for status in (Invoice.Status.DRAFT, Invoice.Status.SETTLED, Invoice.Status.CANCELLED):
        invoice(total="50", status=status)
    assert [row["id"] for row in services.debtors(user, BRANCH_ID)] == [issued.pk]


@pytest.mark.django_db
def test_spec_defect_2_active_membership_required(user: object) -> None:
    inv = invoice(total="50")
    assert services.debtors(user, BRANCH_ID) == []
    grant(user, active=False)
    assert services.debtors(user, BRANCH_ID) == []
    grant(user)
    assert [row["id"] for row in services.debtors(user, BRANCH_ID)] == [inv.pk]


@pytest.mark.django_db
def test_spec_defect_2_membership_must_belong_to_user(user: object) -> None:
    invoice(total="50")
    Membership.objects.create(user_id=999, branch_id=BRANCH_ID, is_active=True)
    assert services.debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
def test_spec_defect_2_requested_branch_must_be_authorized(user: object) -> None:
    invoice(total="50", branch_id=BRANCH_ID)
    grant(user, OTHER_BRANCH_ID)
    assert services.debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
def test_spec_defect_3_pending_and_failed_payments_not_counted(user: object) -> None:
    grant(user)
    inv = invoice(total="300")
    payment(inv, "100", Payment.Status.PENDING)
    payment(inv, "50", Payment.Status.FAILED)
    assert services.debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("300.00")}]


@pytest.mark.django_db
def test_spec_defect_4_negative_and_zero_due_excluded(user: object) -> None:
    grant(user)
    overpaid = invoice(total="100")
    payment(overpaid, "150")
    exact = invoice(total="100")
    payment(exact, "60")
    payment(exact, "40")
    assert services.debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
def test_spec_defect_5_at_most_three_queries_for_100_invoices(user: object) -> None:
    grant(user)
    for _ in range(100):
        inv = invoice(total="100")
        payment(inv, "10")
        payment(inv, "20")
    with CaptureQueriesContext(connection) as captured:
        rows = services.debtors(user, BRANCH_ID)
    count = len(captured.captured_queries)
    assert len(rows) == 100
    assert 0 < count <= 3, f"debtors used {count} queries for 100 invoices"


@pytest.mark.django_db
def test_spec_defect_6_ascending_id_order(user: object) -> None:
    grant(user)
    for pk in (30, 10, 20):
        invoice(pk=pk, total="10")
    assert [row["id"] for row in services.debtors(user, BRANCH_ID)] == [10, 20, 30]


@pytest.mark.django_db
def test_spec_empty_result_when_no_invoices(user: object) -> None:
    grant(user)
    assert services.debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
def test_spec_due_equals_total_without_payments(user: object) -> None:
    grant(user)
    inv = invoice(total="250.50")
    assert services.debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("250.50")}]


@pytest.mark.django_db
def test_spec_multiple_settled_payments_are_summed(user: object) -> None:
    grant(user)
    inv = invoice(total="300")
    payment(inv, "50")
    payment(inv, "70")
    assert services.debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("180.00")}]


@pytest.mark.django_db
def test_spec_unrelated_payments_do_not_change_due(user: object) -> None:
    grant(user)
    inv = invoice(total="300")
    other = invoice(total="300", status=Invoice.Status.SETTLED)
    payment(other, "150")
    assert services.debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("300.00")}]


@pytest.mark.django_db
def test_spec_decimal_precision_is_kept(user: object) -> None:
    grant(user)
    inv = invoice(total="300.50")
    payment(inv, "120.25")
    assert services.debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("180.25")}]
