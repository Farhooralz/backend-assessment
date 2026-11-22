"""Single source of timezone-aware UTC 'now', overridable in tests."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)
