"""Core value objects and the policy abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class QuoteContext:
    """Inputs describing the reservation that are not the money amount."""

    start_hour: int

    def __post_init__(self) -> None:
        if isinstance(self.start_hour, bool) or not isinstance(self.start_hour, int):
            raise TypeError("start_hour must be an int in 0..23")
        if not 0 <= self.start_hour <= 23:
            raise ValueError("start_hour must be between 0 and 23")


@dataclass(frozen=True, slots=True)
class PolicyEffect:
    """One policy's before/after pair, recorded for the breakdown."""

    name: str
    before: Decimal
    after: Decimal

    @property
    def delta(self) -> Decimal:
        """Signed change this policy applied to the running amount."""
        return self.after - self.before


@dataclass(frozen=True, slots=True)
class QuoteResult:
    """Final rounded amount plus an immutable, ordered breakdown."""

    final_amount: Decimal
    breakdown: tuple[PolicyEffect, ...]


class Policy(ABC):
    """A single pricing rule; implementations live outside the engine."""

    name: str = ""

    @abstractmethod
    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        """Return the running amount after this rule, as an exact Decimal."""
