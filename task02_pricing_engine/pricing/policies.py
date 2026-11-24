"""The four concrete policies, including the self-chosen fourth one."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import ClassVar

from pricing.model import (
    STAGE_CREDIT,
    STAGE_DISCOUNT,
    STAGE_MULTIPLIER,
    STAGE_SURCHARGE,
    Policy,
    QuoteContext,
)
from pricing.money import to_decimal


def _positive_multiplier(value: Decimal | int, *, field: str) -> Decimal:
    """Keep one validation path for fixed and per-hour multipliers."""
    multiplier = to_decimal(value, field=field)
    if multiplier <= Decimal("0"):
        raise ValueError(f"{field} must be positive, got {multiplier}")
    return multiplier


@dataclass(frozen=True, slots=True)
class HourMultiplier(Policy):
    """Scale by a fixed multiplier, or by a start-hour schedule (schedule wins)."""

    multiplier: Decimal | None = None
    schedule: Mapping[int, Decimal] = field(default_factory=dict)
    name: str = "HourMultiplier"
    stage: ClassVar[int] = STAGE_MULTIPLIER

    def __post_init__(self) -> None:
        if self.multiplier is not None:
            _positive_multiplier(self.multiplier, field="multiplier")
        validated: dict[int, Decimal] = {}
        for hour, value in self.schedule.items():
            if isinstance(hour, bool) or not isinstance(hour, int):
                raise TypeError(f"schedule hour must be an int, got {type(hour).__name__}")
            if not 0 <= hour <= 23:
                raise ValueError(f"schedule hour must be between 0 and 23, got {hour}")
            validated[hour] = _positive_multiplier(
                value, field=f"schedule multiplier for hour {hour}"
            )
        if self.multiplier is None and not validated:
            raise ValueError("HourMultiplier needs a multiplier or a non-empty schedule")
        object.__setattr__(self, "schedule", MappingProxyType(validated))

    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        multiplier = self.schedule.get(context.start_hour, self.multiplier)
        if multiplier is None:
            raise ValueError(
                f"no multiplier for start_hour={context.start_hour} and no fallback multiplier"
            )
        return amount * multiplier


@dataclass(frozen=True, slots=True)
class PercentDiscount(Policy):
    """Subtract a fractional discount (0.10 means ten percent)."""

    percent: Decimal
    name: str = "PercentDiscount"
    stage: ClassVar[int] = STAGE_DISCOUNT

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
    stage: ClassVar[int] = STAGE_CREDIT

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
    stage: ClassVar[int] = STAGE_SURCHARGE

    def __post_init__(self) -> None:
        to_decimal(self.surcharge, field="surcharge")
        if self.peak_start > self.peak_end:
            raise ValueError("peak_start must not exceed peak_end")

    def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
        if self.peak_start <= context.start_hour <= self.peak_end:
            return amount + self.surcharge
        return amount
