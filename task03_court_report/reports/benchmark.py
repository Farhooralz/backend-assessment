"""Capture the ORM's real SQL and EXPLAIN ANALYZE those exact statements."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from django.db import connection
from django.test.utils import CaptureQueriesContext

from reports.models import Booking, Court
from reports.services import (
    ReportResult,
    naive_court_report,
    optimized_court_report,
)

# A full 50-court page over one realistic week of the 100k seed. A month would
# make the deliberately N+1 service exceed Django's 9,000-query capture buffer.
BENCH_DATE_FROM = date(2026, 6, 1)
BENCH_DATE_TO = date(2026, 6, 7)
BENCH_PAGE = 1
BENCH_PAGE_SIZE = 50

ReportFn = Callable[..., ReportResult]


@dataclass(frozen=True)
class ExplainResult:
    """A captured statement paired with the plan PostgreSQL really produced."""

    label: str
    sql: str
    plan: str


def capture_sql(
    report: ReportFn,
    date_from: date = BENCH_DATE_FROM,
    date_to: date = BENCH_DATE_TO,
    *,
    page: int = BENCH_PAGE,
    page_size: int = BENCH_PAGE_SIZE,
) -> list[str]:
    """Return the SQL Django really executed, with bound literals inlined."""
    with CaptureQueriesContext(connection) as ctx:
        report(date_from, date_to, page=page, page_size=page_size)
    return [entry["sql"] for entry in ctx.captured_queries]


def _first(statements: Iterable[str], predicate: Callable[[str], bool], label: str) -> str:
    """Select the first real statement matching a relation-access shape."""
    for statement in statements:
        if predicate(statement):
            return statement
    msg = f"No captured ORM statement matched {label}"
    raise LookupError(msg)


def naive_real_sql(
    date_from: date = BENCH_DATE_FROM,
    date_to: date = BENCH_DATE_TO,
    *,
    page: int = BENCH_PAGE,
    page_size: int = BENCH_PAGE_SIZE,
) -> dict[str, str]:
    """One real statement per N+1 hop: bookings, payments, then tags."""
    statements = capture_sql(naive_court_report, date_from, date_to, page=page, page_size=page_size)
    return {
        "BEFORE-bookings": _first(
            statements,
            lambda s: (
                'FROM "reports_booking"' in s
                and "reports_payment" not in s
                and "reports_booking_tags" not in s
            ),
            "naive bookings",
        ),
        "BEFORE-payments": _first(
            statements,
            lambda s: 'FROM "reports_payment"' in s and "reports_booking_tags" not in s,
            "naive payments",
        ),
        "BEFORE-tags": _first(
            statements,
            lambda s: "reports_booking_tags" in s,
            "naive tags",
        ),
    }


def optimized_real_sql(
    date_from: date = BENCH_DATE_FROM,
    date_to: date = BENCH_DATE_TO,
    *,
    page: int = BENCH_PAGE,
    page_size: int = BENCH_PAGE_SIZE,
) -> dict[str, str]:
    """The two real set-based statements the optimized service issues."""
    statements = capture_sql(
        optimized_court_report, date_from, date_to, page=page, page_size=page_size
    )
    return {
        "AFTER-aggregates": _first(
            statements,
            lambda s: "reports_payment" in s and "reports_booking_tags" not in s,
            "optimized aggregates",
        ),
        "AFTER-tags": _first(
            statements,
            lambda s: "reports_booking_tags" in s,
            "optimized tags",
        ),
    }


def explain_analyze(sql: str) -> str:
    """Run a genuine EXPLAIN (ANALYZE, BUFFERS) on a captured statement."""
    with connection.cursor() as cur:
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql)
        return "\n".join(row[0] for row in cur.fetchall())


def benchmark(
    date_from: date = BENCH_DATE_FROM,
    date_to: date = BENCH_DATE_TO,
    *,
    page: int = BENCH_PAGE,
    page_size: int = BENCH_PAGE_SIZE,
) -> list[ExplainResult]:
    """Compare real plans for both services at the same filter and page."""
    captured = {
        **naive_real_sql(date_from, date_to, page=page, page_size=page_size),
        **optimized_real_sql(date_from, date_to, page=page, page_size=page_size),
    }
    return [ExplainResult(label, sql, explain_analyze(sql)) for label, sql in captured.items()]


def query_counts(
    date_from: date = BENCH_DATE_FROM,
    date_to: date = BENCH_DATE_TO,
    *,
    page: int = BENCH_PAGE,
    page_size: int = BENCH_PAGE_SIZE,
) -> dict[str, int]:
    """Count real queries and the inputs behind the naive N+1 formula."""
    bookings = Booking.objects.filter(
        confirmed=True, start_date__gte=date_from, start_date__lte=date_to
    ).count()
    courts = Court.objects.count()
    return {
        "bookings": bookings,
        "courts": courts,
        "naive": len(
            capture_sql(naive_court_report, date_from, date_to, page=page, page_size=page_size)
        ),
        "optimized": len(
            capture_sql(optimized_court_report, date_from, date_to, page=page, page_size=page_size)
        ),
        "naive_formula": 2 + courts + 2 * bookings,
    }


def main() -> None:
    """Print the real query counts, statements and plans (via ``django shell``)."""
    counts = query_counts()
    print(
        f"=== Query counts: naive {counts['naive']} ({counts['naive_formula']} by formula), "
        f"optimized {counts['optimized']}; courts {counts['courts']}, "
        f"confirmed bookings in range {counts['bookings']} ==="
    )
    print()
    for result in benchmark(BENCH_DATE_FROM, BENCH_DATE_TO):
        print(f"=== {result.label} ===")
        print("SQL:", " ".join(result.sql.split()))
        print(result.plan)
        print()
