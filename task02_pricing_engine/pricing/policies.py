"""The four concrete policies, including the self-chosen fourth one."""

from dataclasses import dataclass
from decimal import Decimal

from pricing.model import Policy, QuoteContext
from pricing.money import to_decimal


@dataclass(frozen=True, slots=True)
class HourMultiplier(Policy):
    """Scale the amount by the reservation's start-hour multiplier."""

    multiplier: Decimal
    name: str = "HourMultiplier"

    def __post_init__(self) -> None:
        to_decimal(self.multiplier, field="multiplier")

    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        return amount * self.multiplier


@dataclass(frozen=True, slots=True)
class PercentDiscount(Policy):
    """Subtract a fractional discount (0.10 means ten percent)."""

    percent: Decimal
    name: str = "PercentDiscount"

    def __post_init__(self) -> None:
        discount = to_decimal(self.percent, field="percent")
        if not Decimal("0") <= discount <= Decimal("1"):
            raise ValueError("percent must be between 0 and 1")

    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        return amount * (Decimal("1") - self.percent)


@dataclass(frozen=True, slots=True)
class FixedCredit(Policy):
    """Subtract a fixed rial credit, floored at zero by the engine."""

    credit: Decimal
    name: str = "FixedCredit"

    def __post_init__(self) -> None:
        to_decimal(self.credit, field="credit")

    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        return amount - self.credit


@dataclass(frozen=True, slots=True)
class PeakSurcharge(Policy):
    """Self-chosen 4th policy: add a surcharge within an inclusive peak window."""

    surcharge: Decimal
    peak_start: int
    peak_end: int
    name: str = "PeakSurcharge"

    def __post_init__(self) -> None:
        to_decimal(self.surcharge, field="surcharge")
        if self.peak_start > self.peak_end:
            raise ValueError("peak_start must not exceed peak_end")

    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        if self.peak_start <= context.start_hour <= self.peak_end:
            return amount + self.surcharge
        return amount
