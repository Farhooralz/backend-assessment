"""Raw SQL shapes used for the before/after EXPLAIN ANALYZE comparison."""

from datetime import date


def _range(date_from: date, date_to: date) -> str:
    return f"DATE '{date_from.isoformat()}' AND DATE '{date_to.isoformat()}'"


def naive_report_sql(date_from: date, date_to: date) -> str:
    """Join payments and tags in one pass - tag rows multiply summed payments."""
    return f"""
        SELECT c.id, c.name,
               COUNT(DISTINCT b.id) AS booking_count,
               SUM(p.amount) FILTER (WHERE p.successful) AS collected,
               STRING_AGG(DISTINCT t.name, ', ' ORDER BY t.name) AS tags
        FROM reports_court c
        LEFT JOIN reports_booking b
               ON b.court_id = c.id AND b.confirmed
              AND b.start_date BETWEEN {_range(date_from, date_to)}
        LEFT JOIN reports_payment p ON p.booking_id = b.id AND p.successful
        LEFT JOIN reports_booking_tags bt ON bt.booking_id = b.id
        LEFT JOIN reports_tag t ON t.id = bt.tag_id
        GROUP BY c.id, c.name
        ORDER BY c.id
        LIMIT 50
    """


def optimized_report_sql(date_from: date, date_to: date) -> str:
    """The exact grouped aggregate used by optimized_court_report (no tag join)."""
    return f"""
        SELECT b.court_id,
               COUNT(DISTINCT b.id) AS booking_count,
               SUM(p.amount) FILTER (WHERE p.successful) AS collected
        FROM reports_booking b
        LEFT JOIN reports_payment p ON p.booking_id = b.id AND p.successful
        WHERE b.confirmed
          AND b.start_date BETWEEN {_range(date_from, date_to)}
        GROUP BY b.court_id
        ORDER BY b.court_id
    """


def optimized_tags_sql(date_from: date, date_to: date) -> str:
    """The separate distinct-tag query that keeps tag rows out of the SUM."""
    return f"""
        SELECT DISTINCT b.court_id, t.name
        FROM reports_booking b
        JOIN reports_booking_tags bt ON bt.booking_id = b.id
        JOIN reports_tag t ON t.id = bt.tag_id
        WHERE b.confirmed
          AND b.start_date BETWEEN {_range(date_from, date_to)}
        ORDER BY b.court_id, t.name
    """
