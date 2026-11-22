"""Constraint and deliverable tests: no float, extensibility, immutability."""

from decimal import Decimal

import pytest

from pricing import (
    FixedCredit,
    HourMultiplier,
    PeakSurcharge,
    PercentDiscount,
    Policy,
    QuoteContext,
    QuoteEngine,
)


def test_spec_no_float_base_amount_rejected() -> None:
    with pytest.raises(TypeError, match="float"):
        QuoteEngine([]).quote(1000.0, QuoteContext(10))


def test_spec_no_float_policy_parameters_rejected() -> None:
    with pytest.raises(TypeError, match="float"):
        HourMultiplier(1.5)
    with pytest.raises(TypeError, match="float"):
        PercentDiscount(0.10)
    with pytest.raises(TypeError, match="float"):
        FixedCredit(200.0)
    with pytest.raises(TypeError, match="float"):
        PeakSurcharge(500.0, 18, 21)


def test_spec_all_monetary_outputs_are_decimal() -> None:
    result = QuoteEngine(
        [
            HourMultiplier(Decimal("1.5")),
            PercentDiscount(Decimal("0.10")),
            FixedCredit(Decimal("200")),
        ]
    ).quote(Decimal("1000"), QuoteContext(10))
    values = [result.final_amount]
    for effect in result.breakdown:
        values.extend([effect.before, effect.after, effect.delta])
    assert all(isinstance(value, Decimal) for value in values)
    assert not any(isinstance(value, float) for value in values)


def test_spec_add_policy_without_editing_engine() -> None:
    class LoyaltyBonus(Policy):
        name = "LoyaltyBonus"

        def __init__(self, bonus: Decimal) -> None:
            self.bonus = bonus

        def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
            return amount + self.bonus

    engine = QuoteEngine(
        [
            HourMultiplier(Decimal("1.5")),
            LoyaltyBonus(Decimal("50")),
        ]
    )
    result = engine.quote(Decimal("1000"), QuoteContext(10))
    assert result.final_amount == Decimal("1550")
    assert result.breakdown[-1].name == "LoyaltyBonus"


def test_spec_context_is_immutable() -> None:
    context = QuoteContext(10)
    with pytest.raises(AttributeError):
        context.start_hour = 11  # type: ignore[misc]


def test_spec_invalid_context_hour_rejected() -> None:
    with pytest.raises(ValueError):
        QuoteContext(24)
    with pytest.raises(TypeError):
        QuoteContext(10.0)


def test_spec_bool_and_unsupported_money_types_rejected() -> None:
    with pytest.raises(TypeError, match="bool"):
        HourMultiplier(True)
    with pytest.raises(TypeError, match="got str"):
        HourMultiplier("1.5")  # type: ignore[arg-type]


def test_spec_exact_int_money_is_accepted() -> None:
    result = QuoteEngine([FixedCredit(200)]).quote(1000, QuoteContext(10))
    assert result.final_amount == Decimal("800")


def test_spec_out_of_range_policy_values_rejected() -> None:
    with pytest.raises(ValueError, match="percent"):
        PercentDiscount(Decimal("1.10"))
    with pytest.raises(ValueError, match="peak_start"):
        PeakSurcharge(Decimal("500"), 21, 18)
