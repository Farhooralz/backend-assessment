"""Spec tests for the reviewer findings: stage order, start hour, positive multipliers."""

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


def test_spec_engine_enforces_spec_order_for_reversed_input() -> None:
    engine = QuoteEngine(
        [
            FixedCredit(Decimal("200")),
            PercentDiscount(Decimal("0.10")),
            HourMultiplier(Decimal("1.5")),
        ]
    )
    result = engine.quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert result.final_amount == Decimal("1150")
    assert [effect.name for effect in result.breakdown] == [
        "HourMultiplier",
        "PercentDiscount",
        "FixedCredit",
    ]
    assert [(effect.before, effect.after) for effect in result.breakdown] == [
        (Decimal("1000"), Decimal("1500")),
        (Decimal("1500"), Decimal("1350")),
        (Decimal("1350"), Decimal("1150")),
    ]


def test_spec_engine_sorts_stably_within_one_stage() -> None:
    class First(Policy):
        name = "First"
        stage = 50

        def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
            return amount + Decimal("1")

    class Second(Policy):
        name = "Second"
        stage = 50

        def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
            return amount + Decimal("2")

    result = QuoteEngine([Second(), First()]).quote(Decimal("0"), QuoteContext(10))
    assert [effect.name for effect in result.breakdown] == ["Second", "First"]
    assert result.final_amount == Decimal("3")


def test_spec_external_policy_declares_stage_without_editing_the_engine() -> None:
    class Tax(Policy):
        name = "Tax"
        stage = 25

        def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
            return amount * Decimal("1.10")

    engine = QuoteEngine(
        [
            FixedCredit(Decimal("200")),
            Tax(),
            HourMultiplier(Decimal("1.5")),
            PercentDiscount(Decimal("0.10")),
        ]
    )
    result = engine.quote(Decimal("1000"), QuoteContext(10))
    assert [effect.name for effect in result.breakdown] == [
        "HourMultiplier",
        "PercentDiscount",
        "Tax",
        "FixedCredit",
    ]
    assert result.final_amount == Decimal("1285")


def test_spec_external_policy_without_stage_defaults_to_last() -> None:
    class Bonus(Policy):
        name = "Bonus"

        def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
            return amount + Decimal("50")

    engine = QuoteEngine([Bonus(), FixedCredit(Decimal("200")), HourMultiplier(Decimal("1.5"))])
    result = engine.quote(Decimal("1000"), QuoteContext(10))
    assert [effect.name for effect in result.breakdown] == [
        "HourMultiplier",
        "FixedCredit",
        "Bonus",
    ]
    assert result.final_amount == Decimal("1350")


def test_spec_engine_rejects_non_integer_policy_stage() -> None:
    class Bad(Policy):
        name = "Bad"
        stage = "10"  # type: ignore[assignment]

        def apply(self, amount: Decimal, context: QuoteContext) -> Decimal:
            return amount

    with pytest.raises(TypeError, match="stage"):
        QuoteEngine([Bad()])


def test_spec_hour_multiplier_schedule_uses_start_hour() -> None:
    policy = HourMultiplier(schedule={9: Decimal("1.2"), 18: Decimal("1.8")})
    engine = QuoteEngine([policy])
    morning = engine.quote(Decimal("1000"), QuoteContext(9))
    evening = engine.quote(Decimal("1000"), QuoteContext(18))
    assert morning.final_amount == Decimal("1200")
    assert evening.final_amount == Decimal("1800")
    assert morning.final_amount != evening.final_amount


def test_spec_hour_multiplier_schedule_overrides_explicit_fallback() -> None:
    policy = HourMultiplier(multiplier=Decimal("1.5"), schedule={9: Decimal("2")})
    assert policy.apply(Decimal("1000"), QuoteContext(9)) == Decimal("2000")
    assert policy.apply(Decimal("1000"), QuoteContext(10)) == Decimal("1500")


def test_spec_hour_multiplier_missing_hour_without_fallback_raises() -> None:
    policy = HourMultiplier(schedule={9: Decimal("1.2")})
    with pytest.raises(ValueError, match="start_hour"):
        policy.apply(Decimal("1000"), QuoteContext(10))


def test_spec_hour_multiplier_rejects_non_positive_multipliers() -> None:
    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValueError, match="positive"):
            HourMultiplier(bad)
        with pytest.raises(ValueError, match="positive"):
            HourMultiplier(schedule={9: bad})


def test_spec_hour_multiplier_requires_a_multiplier_source() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        HourMultiplier()


def test_spec_hour_multiplier_rejects_invalid_schedule_hours() -> None:
    with pytest.raises(ValueError, match="hour"):
        HourMultiplier(schedule={24: Decimal("1.5")})
    with pytest.raises(TypeError, match="hour"):
        HourMultiplier(schedule={"9": Decimal("1.5")})  # type: ignore[dict-item]


def test_spec_hour_multiplier_schedule_is_immutable() -> None:
    policy = HourMultiplier(schedule={9: Decimal("1.2")})
    with pytest.raises(TypeError):
        policy.schedule[10] = Decimal("3")  # type: ignore[index]


def test_spec_fourth_policy_credit_is_last_in_breakdown() -> None:
    engine = QuoteEngine(
        [
            PeakSurcharge(Decimal("500"), 18, 21),
            FixedCredit(Decimal("200")),
            PercentDiscount(Decimal("0.10")),
            HourMultiplier(Decimal("1.5")),
        ]
    )
    peak = engine.quote(Decimal("1000"), QuoteContext(19))
    assert peak.final_amount == Decimal("1650")
    assert [effect.name for effect in peak.breakdown] == [
        "HourMultiplier",
        "PercentDiscount",
        "PeakSurcharge",
        "FixedCredit",
    ]
