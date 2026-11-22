"""Capture the ORM's real SQL and EXPLAIN ANALYZE those exact statements."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from django.db import connection
from django.test.utils import CaptureQueriesContext

from reports.services import (
    DATE_FROM,
    DATE_TO,
    ReportResult,
    naive_court_report,
    optimized_court_report,
)

BENCH_DATE = date(2026, 6, 16)
# The seed correlates court index with start_date; page 4 starts at court 7,
# which actually has confirmed bookings on BENCH_DATE in the 100k dataset.
BENCH_PAGE = 4
BENCH_PAGE_SIZE = 2

ReportFn = Callable[..., ReportResult]


@dataclass(frozen=True)
class ExplainResult:
    """A captured statement paired with the plan PostgreSQL really produced."""

    label: str
    sql: str
    plan: str


def capture_sql(
    report: ReportFn,
    date_from: date = DATE_FROM,
    date_to: date = DATE_TO,
    *,
    page: int = 1,
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
    date_from: date = DATE_FROM,
    date_to: date = DATE_TO,
    *,
    page: int = 1,
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
    date_from: date = DATE_FROM,
    date_to: date = DATE_TO,
    *,
    page: int = 1,
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
    date_from: date = DATE_FROM,
    date_to: date = DATE_TO,
    *,
    page: int = 1,
    page_size: int = BENCH_PAGE_SIZE,
) -> list[ExplainResult]:
    """Compare real plans for both services at the same filter and page."""
    captured = {
        **naive_real_sql(date_from, date_to, page=page, page_size=page_size),
        **optimized_real_sql(date_from, date_to, page=page, page_size=page_size),
    }
    return [ExplainResult(label, sql, explain_analyze(sql)) for label, sql in captured.items()]


def main() -> None:
    """Print the real statements and plans (run through ``django shell``)."""
    for result in benchmark(BENCH_DATE, BENCH_DATE, page=BENCH_PAGE, page_size=BENCH_PAGE_SIZE):
        print(f"=== {result.label} ===")
        print("SQL:", " ".join(result.sql.split()))
        print(result.plan)
        print()
