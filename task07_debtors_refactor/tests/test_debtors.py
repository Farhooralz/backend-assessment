"""Contract, regression, and defect tests for the debtors report.

Every debtors case is parametrized over ``impl in {legacy, services}``.
Regression / happy-path cases must pass on both implementations; each
``test_spec_defect_*`` case is ``xfail(strict=True)`` on ``legacy`` (the defect
is reproduced there) and must pass on ``services``.
"""

import inspect
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledger import legacy, services
from ledger.models import Invoice, Membership, Payment

BRANCH_ID = 7
OTHER_BRANCH_ID = 99

IMPL_MODULES = {"legacy": legacy, "services": services}
BOTH = ["legacy", "services"]
DEFECT_IMPLS = [
    pytest.param(
        "legacy",
        marks=pytest.mark.xfail(strict=True, reason="defect is present in the legacy function"),
        id="legacy",
    ),
    pytest.param("services", id="services"),
]


@pytest.fixture
def debtors(impl: str):
    """Resolve the parametrized implementation name to its function."""
    return IMPL_MODULES[impl].debtors


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
@pytest.mark.parametrize("impl", BOTH)
def test_spec_signature_and_output_keys_preserved(debtors, user: object) -> None:
    assert list(inspect.signature(debtors).parameters) == ["user", "branch_id"]
    grant(user)
    inv = invoice()
    rows = debtors(user, BRANCH_ID)
    assert len(rows) == 1
    assert set(rows[0]) == {"id", "due"}
    assert rows[0]["id"] == inv.pk


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_regression_positive_debt_and_keys(debtors, user: object) -> None:
    """Characterization: both implementations agree on a plain issued invoice."""
    grant(user)
    inv = invoice(total="300")
    payment(inv, "100")
    assert debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("200.00")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_regression_zero_debt_is_skipped(debtors, user: object) -> None:
    """Characterization: a fully paid invoice produces no row in either implementation."""
    grant(user)
    inv = invoice(total="100")
    payment(inv, "100")
    assert debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_money_is_decimal(debtors, user: object) -> None:
    grant(user)
    inv = invoice(total="300.50")
    payment(inv, "100.25")
    due = debtors(user, BRANCH_ID)[0]["due"]
    assert isinstance(due, Decimal)
    assert not isinstance(due, float)


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_empty_result_when_no_invoices(debtors, user: object) -> None:
    grant(user)
    assert debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_due_equals_total_without_payments(debtors, user: object) -> None:
    grant(user)
    inv = invoice(total="250.50")
    assert debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("250.50")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_multiple_settled_payments_are_summed(debtors, user: object) -> None:
    grant(user)
    inv = invoice(total="300")
    payment(inv, "50")
    payment(inv, "70")
    assert debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("180.00")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", BOTH)
def test_spec_decimal_precision_is_kept(debtors, user: object) -> None:
    grant(user)
    inv = invoice(total="300.50")
    payment(inv, "120.25")
    assert debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("180.25")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_1_only_issued_invoices(debtors, user: object) -> None:
    grant(user)
    issued = invoice(total="50")
    for status in (Invoice.Status.DRAFT, Invoice.Status.SETTLED, Invoice.Status.CANCELLED):
        invoice(total="50", status=status)
    assert [row["id"] for row in debtors(user, BRANCH_ID)] == [issued.pk]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_1_acceptance_status_and_other_branch_excluded(debtors, user: object) -> None:
    grant(user)
    good = invoice(total="300")
    for status in (Invoice.Status.DRAFT, Invoice.Status.SETTLED, Invoice.Status.CANCELLED):
        invoice(total="300", status=status)
    invoice(total="300", branch_id=OTHER_BRANCH_ID)
    assert debtors(user, BRANCH_ID) == [{"id": good.pk, "due": Decimal("300.00")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_1_unrelated_payments_do_not_change_due(debtors, user: object) -> None:
    grant(user)
    inv = invoice(total="300")
    other = invoice(total="300", status=Invoice.Status.SETTLED)
    payment(other, "150")
    assert debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("300.00")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_2_active_membership_required(debtors, user: object) -> None:
    inv = invoice(total="50")
    assert debtors(user, BRANCH_ID) == []
    grant(user, active=False)
    assert debtors(user, BRANCH_ID) == []
    grant(user)
    assert [row["id"] for row in debtors(user, BRANCH_ID)] == [inv.pk]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_2_membership_must_belong_to_user(debtors, user: object) -> None:
    invoice(total="50")
    Membership.objects.create(user_id=999, branch_id=BRANCH_ID, is_active=True)
    assert debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_2_requested_branch_must_be_authorized(debtors, user: object) -> None:
    invoice(total="50", branch_id=BRANCH_ID)
    grant(user, OTHER_BRANCH_ID)
    assert debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_3_pending_and_failed_payments_not_counted(debtors, user: object) -> None:
    grant(user)
    inv = invoice(total="300")
    payment(inv, "100", Payment.Status.PENDING)
    payment(inv, "50", Payment.Status.FAILED)
    assert debtors(user, BRANCH_ID) == [{"id": inv.pk, "due": Decimal("300.00")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_3_sample_invoice_300_due_180(debtors, user: object) -> None:
    grant(user)
    inv = invoice(pk=300, total="300")
    payment(inv, "120", Payment.Status.SETTLED)
    payment(inv, "100", Payment.Status.PENDING)
    assert debtors(user, BRANCH_ID) == [{"id": 300, "due": Decimal("180.00")}]


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_4_negative_and_zero_due_excluded(debtors, user: object) -> None:
    grant(user)
    overpaid = invoice(total="100")
    payment(overpaid, "150")
    exact = invoice(total="100")
    payment(exact, "60")
    payment(exact, "40")
    assert debtors(user, BRANCH_ID) == []


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_5_at_most_three_queries_for_100_invoices(
    debtors, impl: str, user: object
) -> None:
    grant(user)
    for _ in range(100):
        inv = invoice(total="100")
        payment(inv, "10")
        payment(inv, "20")
    with CaptureQueriesContext(connection) as captured:
        rows = debtors(user, BRANCH_ID)
    count = len(captured.captured_queries)
    assert len(rows) == 100
    assert 0 < count <= 3, f"debtors used {count} queries for 100 invoices"
    if impl == "services":
        assert count == 2, f"services used {count} queries, expected 2"


@pytest.mark.django_db
@pytest.mark.parametrize("impl", DEFECT_IMPLS)
def test_spec_defect_6_ascending_id_order(debtors, user: object) -> None:
    grant(user)
    for pk in (30, 10, 20):
        invoice(pk=pk, total="10")
    assert [row["id"] for row in debtors(user, BRANCH_ID)] == [10, 20, 30]
