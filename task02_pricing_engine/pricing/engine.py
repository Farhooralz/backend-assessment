"""The quote engine: an ordered composition of policies."""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from pricing.model import Policy, PolicyEffect, QuoteContext, QuoteResult
from pricing.money import to_decimal

_RIAL = Decimal("1")
_ZERO = Decimal("0")


class QuoteEngine:
    """Apply policies in order, clamp at zero, round to rials only at the end."""

    def __init__(self, policies: Iterable[Policy]) -> None:
        self._policies = tuple(policies)

    def quote(self, base_amount: Decimal | int, context: QuoteContext) -> QuoteResult:
        """Return the final rial amount and the per-policy breakdown."""
        amount = to_decimal(base_amount, field="base_amount")
        effects: list[PolicyEffect] = []
        for policy in self._policies:
            before = amount
            after = max(_ZERO, policy.apply(amount, context))
            effects.append(PolicyEffect(name=policy.name, before=before, after=after))
            amount = after
        final = amount.quantize(_RIAL, rounding=ROUND_HALF_UP)
        return QuoteResult(final_amount=final, breakdown=tuple(effects))
