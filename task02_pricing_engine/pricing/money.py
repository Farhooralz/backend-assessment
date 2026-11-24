"""Money helpers that keep every amount an exact Decimal."""

from decimal import Decimal


def to_decimal(value: Decimal | int, *, field: str) -> Decimal:
    """Coerce an exact numeric to Decimal; reject float to prevent binary error."""
    if isinstance(value, bool):
        raise TypeError(f"{field} must be a Decimal (or int), not bool")
    if isinstance(value, float):
        raise TypeError(f"{field} must be a Decimal, not float; use Decimal('...')")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    raise TypeError(f"{field} must be a Decimal (or int), got {type(value).__name__}")
