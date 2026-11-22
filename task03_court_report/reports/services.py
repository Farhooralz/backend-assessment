"""Per-court report logic: a measured naive version and a bounded-query version."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum

from reports.models import Booking, Court

DATE_FROM = date(2026, 1, 1)
DATE_TO = date(2026, 12, 31)


@dataclass(frozen=True)
class CourtReportRow:
    court_id: int
    court_name: str
    booking_count: int
    collected: Decimal
    tags: list[str]


ReportResult = tuple[list[CourtReportRow], int]


def _date_filter(date_from: date, date_to: date) -> dict:
    return {
        "confirmed": True,
        "start_date__gte": date_from,
        "start_date__lte": date_to,
    }


def naive_court_report(
    date_from: date = DATE_FROM,
    date_to: date = DATE_TO,
    *,
    page: int = 1,
    page_size: int = 50,
) -> ReportResult:
    """Walk bookings per court, following each payments/tags relation (N+1)."""
    paginator = Paginator(Court.objects.order_by("id"), page_size)
    page_obj = paginator.page(page)
    rows: list[CourtReportRow] = []

    for court in page_obj.object_list:
        bookings = list(court.bookings.filter(**_date_filter(date_from, date_to)))
        collected = Decimal("0")
        names: set[str] = set()
        for booking in bookings:
            for payment in booking.payments.all():
                if payment.successful:
                    collected += payment.amount
            for tag in booking.tags.all():
                names.add(tag.name)
        rows.append(CourtReportRow(court.id, court.name, len(bookings), collected, sorted(names)))
    return rows, paginator.count


def optimized_court_report(
    date_from: date = DATE_FROM,
    date_to: date = DATE_TO,
    *,
    page: int = 1,
    page_size: int = 50,
) -> ReportResult:
    """Aggregate bookings/payments and tags separately so joins never multiply sums."""
    paginator = Paginator(Court.objects.order_by("id"), page_size)
    page_obj = paginator.page(page)
    courts = list(page_obj.object_list)
    court_ids = [court.id for court in courts]
    if not court_ids:
        return [], paginator.count

    filt = _date_filter(date_from, date_to)

    # Payments are summed without joining tags; DISTINCT id compensates for the
    # payment join duplicating a booking row (one row per payment).
    aggregates = {
        row["court_id"]: row
        for row in Booking.objects.filter(court_id__in=court_ids, **filt)
        .values("court_id")
        .annotate(
            booking_count=Count("id", distinct=True),
            collected=Sum("payments__amount", filter=Q(payments__successful=True)),
        )
    }

    # Tags come from their own query, so tag rows cannot duplicate payment amounts.
    tag_names: dict[int, set[str]] = {}
    for court_id, name in (
        Booking.objects.filter(court_id__in=court_ids, **filt)
        .values_list("court_id", "tags__name")
        .distinct()
    ):
        tag_names.setdefault(court_id, set()).add(name)

    rows = [
        CourtReportRow(
            court.id,
            court.name,
            aggregates.get(court.id, {}).get("booking_count", 0),
            aggregates.get(court.id, {}).get("collected") or Decimal("0"),
            sorted(tag_names.get(court.id, set())),
        )
        for court in courts
    ]
    return rows, paginator.count
