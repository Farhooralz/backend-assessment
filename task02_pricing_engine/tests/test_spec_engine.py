"""Spec acceptance tests for the quote engine."""

from decimal import Decimal

from pricing import (
    FixedCredit,
    HourMultiplier,
    PercentDiscount,
    PolicyEffect,
    QuoteContext,
    QuoteEngine,
)


def _standard_engine(credit: Decimal) -> QuoteEngine:
    """Build the three-policy chain described in the spec."""
    return QuoteEngine(
        [
            HourMultiplier(Decimal("1.5")),
            PercentDiscount(Decimal("0.10")),
            FixedCredit(credit),
        ]
    )


def test_spec_acceptance_full_combination_yields_1150() -> None:
    result = _standard_engine(Decimal("200")).quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert result.final_amount == Decimal("1150")


def test_spec_acceptance_credit_larger_than_amount_clamps_to_zero() -> None:
    result = _standard_engine(Decimal("2000")).quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert result.final_amount == Decimal("0")


def test_spec_acceptance_rerun_is_deterministic() -> None:
    engine = _standard_engine(Decimal("200"))
    first = engine.quote(Decimal("1000"), QuoteContext(start_hour=10))
    second = engine.quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert first == second


def test_spec_behavior_policy_order_is_multiplier_discount_credit() -> None:
    result = _standard_engine(Decimal("200")).quote(Decimal("1000"), QuoteContext(start_hour=10))
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
    assert [effect.delta for effect in result.breakdown] == [
        Decimal("500"),
        Decimal("-150"),
        Decimal("-200"),
    ]


def test_spec_behavior_amount_is_never_negative() -> None:
    result = _standard_engine(Decimal("2000")).quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert result.final_amount >= Decimal("0")
    assert all(effect.after >= Decimal("0") for effect in result.breakdown)


def test_spec_behavior_rounding_half_up_only_at_the_end() -> None:
    # Intermediate rounding after the multiplier would give 1005 * 0.9 = 904.5
    # -> 905; rounding only at the end gives 904.41 -> 904.
    engine = QuoteEngine(
        [
            HourMultiplier(Decimal("1.0049")),
            PercentDiscount(Decimal("0.10")),
        ]
    )
    result = engine.quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert result.final_amount == Decimal("904")

    # 1000 * 1.0005 = 1000.5 must round HALF_UP (not DOWN) to 1001.
    half_up = QuoteEngine([HourMultiplier(Decimal("1.0005"))]).quote(
        Decimal("1000"), QuoteContext(start_hour=10)
    )
    assert half_up.final_amount == Decimal("1001")


def test_spec_behavior_output_has_final_amount_and_breakdown() -> None:
    result = _standard_engine(Decimal("200")).quote(Decimal("1000"), QuoteContext(start_hour=10))
    assert isinstance(result.final_amount, Decimal)
    assert isinstance(result.breakdown, tuple)
    assert len(result.breakdown) == 3
    assert all(isinstance(effect, PolicyEffect) for effect in result.breakdown)


def test_spec_empty_policy_list_returns_rounded_base() -> None:
    result = QuoteEngine([]).quote(Decimal("1000.5"), QuoteContext(start_hour=10))
    assert result.final_amount == Decimal("1001")
    assert result.breakdown == ()
