"""Round-2 regression tests: findings from the external review, red before fixes."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from reports.benchmark import benchmark, query_counts
from reports.models import Booking, Branch, Court, Payment, Tag
from reports.services import naive_court_report, optimized_court_report

DATE_FROM = date(2026, 1, 1)
DATE_TO = date(2026, 12, 31)
IN_RANGE = date(2026, 6, 15)


def _courts(count: int, prefix: str = "R2 Court") -> list[Court]:
    branch = Branch.objects.create(name=f"{prefix} Branch")
    return Court.objects.bulk_create(
        [Court(branch=branch, name=f"{prefix} {i}") for i in range(count)]
    )


def _dense_fixture(count: int = 50) -> list[Court]:
    """Two confirmed bookings, two payments and three tags per court."""
    courts = _courts(count)
    tags = Tag.objects.bulk_create([Tag(name=f"r2-tag-{i}") for i in range(3)])
    bookings = Booking.objects.bulk_create(
        [
            Booking(court=c, start_date=date(2026, 6, 3), confirmed=True)
            for c in courts
            for _ in range(2)
        ]
    )
    Payment.objects.bulk_create(
        [Payment(booking=b, amount=Decimal("10.00"), successful=True) for b in bookings]
    )
    Booking.tags.through.objects.bulk_create(
        [Booking.tags.through(booking_id=b.id, tag_id=t.id) for b in bookings for t in tags]
    )
    return courts


@pytest.fixture
def untagged(db) -> tuple[Court, Court, Court]:
    tagged, only_untagged, empty = _courts(3, prefix="Untagged")
    tag = Tag.objects.create(name="only-tag")
    first = Booking.objects.create(court=tagged, start_date=IN_RANGE, confirmed=True)
    first.tags.add(tag)
    Booking.objects.create(court=tagged, start_date=IN_RANGE, confirmed=True)
    Booking.objects.create(court=only_untagged, start_date=IN_RANGE, confirmed=True)
    return tagged, only_untagged, empty


@pytest.mark.django_db
def test_spec_untagged_booking_does_not_add_none_tag(untagged: tuple[Court, Court, Court]) -> None:
    """A left join yields NULL for an untagged booking; the tag list must stay empty."""
    _, only_untagged, _ = untagged
    optimized_rows, _ = optimized_court_report(DATE_FROM, DATE_TO)
    row = next(r for r in optimized_rows if r.court_id == only_untagged.id)
    assert row.tags == []


@pytest.mark.django_db
def test_spec_naive_equals_optimized_with_untagged_bookings(
    untagged: tuple[Court, Court, Court],
) -> None:
    """Row-by-row equivalence with mixed tagged/untagged, all-untagged and empty courts."""
    tagged, only_untagged, empty = untagged
    naive_rows, naive_total = naive_court_report(DATE_FROM, DATE_TO)
    optimized_rows, optimized_total = optimized_court_report(DATE_FROM, DATE_TO)
    assert naive_total == optimized_total == 3
    assert naive_rows == optimized_rows
    assert [r.tags for r in optimized_rows] == [["only-tag"], [], []]
    assert [r.court_id for r in optimized_rows] == [tagged.id, only_untagged.id, empty.id]


@pytest.mark.django_db
def test_spec_exact_query_counts_and_all_row_values_50_courts(
    django_assert_num_queries,
) -> None:
    """Optimized is exactly 4 queries; naive is exactly 2 + courts + 2 * bookings."""
    courts = _dense_fixture(50)
    with django_assert_num_queries(4):
        optimized_rows, total = optimized_court_report(DATE_FROM, DATE_TO)
    with django_assert_num_queries(252):  # count + court page + 50 booking + 100 * 2 relation
        naive_rows, naive_total = naive_court_report(DATE_FROM, DATE_TO)

    assert total == naive_total == 50
    assert naive_rows == optimized_rows
    assert [r.court_id for r in optimized_rows] == [c.id for c in courts]
    for row in optimized_rows:
        assert row.booking_count == 2
        assert row.collected == Decimal("20.00")
        assert row.tags == ["r2-tag-0", "r2-tag-1", "r2-tag-2"]

    # The helper behind the README's benchmark command prints the same numbers.
    assert query_counts(DATE_FROM, DATE_TO, page=1, page_size=50) == {
        "bookings": 100,
        "courts": 50,
        "naive": 252,
        "optimized": 4,
        "naive_formula": 252,
    }


@pytest.mark.django_db
def test_spec_out_of_range_page_clamps(db) -> None:
    """page < 1 and page > last both resolve to a real page instead of EmptyPage."""
    courts = _courts(3)
    for report in (naive_court_report, optimized_court_report):
        first_rows, total = report(DATE_FROM, DATE_TO, page=0, page_size=2)
        last_rows, _ = report(DATE_FROM, DATE_TO, page=99, page_size=2)
        assert total == 3
        assert [r.court_id for r in first_rows] == [courts[0].id, courts[1].id]
        assert [r.court_id for r in last_rows] == [courts[2].id]


@pytest.mark.django_db
def test_spec_page_size_is_capped_at_100(db) -> None:
    """A caller cannot ask for an unbounded page."""
    courts = _courts(120)
    for report in (naive_court_report, optimized_court_report):
        rows, total = report(DATE_FROM, DATE_TO, page=1, page_size=1000)
        assert total == 120
        assert len(rows) == 100
        assert rows[0].court_id == courts[0].id
        assert rows[-1].court_id == courts[99].id


@pytest.mark.django_db
@pytest.mark.timeout(120)
def test_spec_seed_decouples_court_from_confirmed(db) -> None:
    """Every seeded court has confirmed bookings, in the year and in a summer month."""
    call_command("seed_bookings", "--bookings", "2000", verbosity=0)
    seeded = Court.objects.filter(name__startswith="Seed Court")
    court_ids = set(seeded.values_list("id", flat=True))
    confirmed_all = set(
        Booking.objects.filter(confirmed=True, court_id__in=court_ids).values_list(
            "court_id", flat=True
        )
    )
    assert confirmed_all == court_ids

    confirmed_summer = set(
        Booking.objects.filter(
            confirmed=True,
            court_id__in=court_ids,
            start_date__gte=date(2026, 1, 1),
            start_date__lte=date(2026, 1, 30),
        ).values_list("court_id", flat=True)
    )
    assert confirmed_summer == court_ids


@pytest.mark.django_db
@pytest.mark.timeout(120)
def test_spec_seed_is_idempotent_and_resettable(db) -> None:
    """Re-seeding adds nothing; --reset replaces the previous dataset."""
    call_command("seed_bookings", "--bookings", "200", verbosity=0)
    call_command("seed_bookings", "--bookings", "200", verbosity=0)
    assert Booking.objects.count() == 200
    call_command("seed_bookings", "--bookings", "200", "--reset", verbosity=0)
    assert Booking.objects.count() == 200
    assert Payment.objects.count() == 400


@pytest.mark.django_db
def test_spec_benchmark_defaults_to_50_court_page_and_week_range(db) -> None:
    """The documented EXPLAIN command really captures a 50-court, week-long page."""
    _dense_fixture(50)
    results = benchmark()
    assert len(results) == 5
    aggregates = next(r for r in results if r.label == "AFTER-aggregates").sql
    assert '"reports_booking"."court_id" IN (' in aggregates
    assert ">= '2026-06-01'::date" in aggregates
    assert "<= '2026-06-07'::date" in aggregates
    assert "reports_booking_tags" not in aggregates


@pytest.mark.django_db
def test_spec_optimized_excludes_unconfirmed_bookings(db) -> None:
    """An unconfirmed booking in range must not affect the optimized count."""
    court = _courts(1)[0]
    Booking.objects.create(court=court, start_date=IN_RANGE, confirmed=False)
    rows, _ = optimized_court_report(DATE_FROM, DATE_TO)
    assert rows[0].booking_count == 0


@pytest.mark.django_db
def test_spec_optimized_counts_one_booking_with_many_payments_once(db) -> None:
    """DISTINCT id prevents the payment join from inflating the booking count."""
    court = _courts(1)[0]
    booking = Booking.objects.create(court=court, start_date=IN_RANGE, confirmed=True)
    Payment.objects.bulk_create(
        [Payment(booking=booking, amount=Decimal("10.00"), successful=True) for _ in range(3)]
    )
    rows, _ = optimized_court_report(DATE_FROM, DATE_TO)
    assert rows[0].booking_count == 1
    assert rows[0].collected == Decimal("30.00")


@pytest.mark.django_db
def test_spec_optimized_end_date_is_inclusive(db) -> None:
    """A booking exactly on `to` is counted by the optimized service."""
    court = _courts(1)[0]
    Booking.objects.create(court=court, start_date=IN_RANGE, confirmed=True)
    rows, _ = optimized_court_report(IN_RANGE, IN_RANGE)
    assert rows[0].booking_count == 1
