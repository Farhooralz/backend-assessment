"""Spec tests for the naive and optimized per-court financial report."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from reports.benchmark import (
    benchmark,
    capture_sql,
    naive_real_sql,
    optimized_real_sql,
)
from reports.models import Booking, Branch, Court, Payment, Tag
from reports.services import naive_court_report, optimized_court_report

DATE_FROM = date(2026, 1, 1)
DATE_TO = date(2026, 12, 31)
IN_RANGE = date(2026, 6, 15)
OUT_OF_RANGE = date(2027, 6, 15)


def _courts(count: int) -> list[Court]:
    branch = Branch.objects.create(name="Branch")
    return Court.objects.bulk_create(
        [Court(branch=branch, name=f"Court {i}") for i in range(count)]
    )


def _booking(court: Court, start: date, confirmed: bool = True) -> Booking:
    return Booking.objects.create(court=court, start_date=start, confirmed=confirmed)


@pytest.fixture
def sample(db) -> tuple[Court, Court]:
    court, empty = _courts(2)
    tags = [Tag.objects.create(name=name) for name in ("alpha", "beta", "gamma")]
    booking = _booking(court, IN_RANGE)
    booking.tags.set(tags)
    Payment.objects.create(booking=booking, amount=Decimal("100.00"), successful=True)
    Payment.objects.create(booking=booking, amount=Decimal("100.00"), successful=True)
    Payment.objects.create(booking=booking, amount=Decimal("30.00"), successful=False)
    return court, empty


@pytest.mark.django_db
def test_spec_sample_confirmed_booking_count_1_collected_200(sample) -> None:
    court, _ = sample
    for report in (naive_court_report, optimized_court_report):
        rows, _ = report(DATE_FROM, DATE_TO)
        row = next(r for r in rows if r.court_id == court.id)
        assert row.booking_count == 1
        assert row.collected == Decimal("200.00")


@pytest.mark.django_db
def test_spec_sample_three_distinct_tags(sample) -> None:
    court, _ = sample
    for report in (naive_court_report, optimized_court_report):
        rows, _ = report(DATE_FROM, DATE_TO)
        row = next(r for r in rows if r.court_id == court.id)
        assert row.tags == ["alpha", "beta", "gamma"]


@pytest.mark.django_db
def test_spec_empty_court_count_zero_and_amount_zero(sample) -> None:
    _, empty = sample
    for report in (naive_court_report, optimized_court_report):
        rows, _ = report(DATE_FROM, DATE_TO)
        row = next(r for r in rows if r.court_id == empty.id)
        assert row.booking_count == 0
        assert row.collected == Decimal("0")
        assert row.tags == []


@pytest.mark.django_db
def test_spec_failed_payment_excluded_from_collected(sample) -> None:
    court, _ = sample
    rows, _ = optimized_court_report(DATE_FROM, DATE_TO)
    assert next(r for r in rows if r.court_id == court.id).collected == Decimal("200.00")


@pytest.mark.django_db
def test_spec_date_filter_on_booking_start_date(sample) -> None:
    court, _ = sample
    _booking(court, OUT_OF_RANGE)
    _booking(court, date(2025, 12, 31))
    for report in (naive_court_report, optimized_court_report):
        rows, _ = report(DATE_FROM, DATE_TO)
        assert next(r for r in rows if r.court_id == court.id).booking_count == 1
        rows, _ = report(IN_RANGE, IN_RANGE)
        assert next(r for r in rows if r.court_id == court.id).booking_count == 1
        rows, _ = report(OUT_OF_RANGE, OUT_OF_RANGE)
        assert next(r for r in rows if r.court_id == court.id).booking_count == 1
        rows, _ = report(date(2028, 1, 1), date(2028, 1, 1))
        assert next(r for r in rows if r.court_id == court.id).booking_count == 0


@pytest.mark.django_db
def test_spec_naive_query_count_is_n_plus_1(db) -> None:
    courts = _courts(3)
    tag = Tag.objects.create(name="t")
    for court in courts:
        for _ in range(2):
            _booking(court, IN_RANGE).tags.add(tag)
    with CaptureQueriesContext(connection) as ctx:
        naive_court_report(DATE_FROM, DATE_TO)
    assert len(ctx.captured_queries) >= 10


@pytest.mark.django_db
def test_spec_optimized_at_most_5_queries_for_50_courts(db) -> None:
    courts = _courts(50)
    tags = Tag.objects.bulk_create([Tag(name=f"t{i}") for i in range(3)])
    bookings = Booking.objects.bulk_create(
        [Booking(court=c, start_date=IN_RANGE, confirmed=True) for c in courts for _ in range(2)]
    )
    Payment.objects.bulk_create(
        [Payment(booking=b, amount=Decimal("10.00"), successful=True) for b in bookings]
    )
    Booking.tags.through.objects.bulk_create(
        [Booking.tags.through(booking_id=b.id, tag_id=t.id) for b in bookings for t in tags]
    )
    with CaptureQueriesContext(connection) as ctx:
        rows, total = optimized_court_report(DATE_FROM, DATE_TO)
    assert total == 50
    assert len(rows) == 50
    assert len(ctx.captured_queries) <= 5


@pytest.mark.django_db
def test_spec_naive_equals_optimized(sample) -> None:
    court, empty = sample
    extra = _booking(court, IN_RANGE)
    extra.tags.add(Tag.objects.get(name="alpha"))
    Payment.objects.create(booking=extra, amount=Decimal("50.00"), successful=True)
    _booking(court, OUT_OF_RANGE)
    _booking(empty, IN_RANGE, confirmed=False)
    naive_rows, naive_total = naive_court_report(DATE_FROM, DATE_TO)
    optimized_rows, optimized_total = optimized_court_report(DATE_FROM, DATE_TO)
    assert naive_total == optimized_total == 2
    assert naive_rows == optimized_rows


@pytest.mark.django_db
def test_spec_pagination_page_size_50(db) -> None:
    courts = _courts(120)
    rows, total = optimized_court_report(DATE_FROM, DATE_TO, page=2, page_size=50)
    assert total == 120
    assert len(rows) == 50
    assert rows[0].court_id == courts[50].id


@pytest.mark.django_db
def test_spec_explain_analyze_comparison(sample) -> None:
    results = benchmark(DATE_FROM, DATE_TO, page_size=2)
    assert {result.label for result in results} == {
        "BEFORE-bookings",
        "BEFORE-payments",
        "BEFORE-tags",
        "AFTER-aggregates",
        "AFTER-tags",
    }
    for result in results:
        assert result.sql.strip().upper().startswith("SELECT")
        assert "Planning Time:" in result.plan
        assert "Execution Time:" in result.plan


@pytest.mark.django_db
def test_spec_benchmark_explains_real_orm_statements(sample) -> None:
    """Every EXPLAINed statement was captured verbatim from a service call."""
    naive_all = capture_sql(naive_court_report, DATE_FROM, DATE_TO, page_size=2)
    naive_selected = naive_real_sql(DATE_FROM, DATE_TO, page_size=2)
    assert set(naive_selected.values()) <= set(naive_all)
    assert "reports_booking_tags" in naive_selected["BEFORE-tags"]
    assert "reports_payment" in naive_selected["BEFORE-payments"]

    optimized_all = capture_sql(optimized_court_report, DATE_FROM, DATE_TO, page_size=2)
    optimized_selected = optimized_real_sql(DATE_FROM, DATE_TO, page_size=2)
    assert set(optimized_selected.values()) <= set(optimized_all)
    assert "reports_payment" in optimized_selected["AFTER-aggregates"]
    assert "reports_booking_tags" in optimized_selected["AFTER-tags"]
