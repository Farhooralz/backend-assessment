"""Per-policy tests plus the shared contract test run against every policy."""

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

ALL_POLICIES = [
    HourMultiplier(Decimal("1.5")),
    PercentDiscount(Decimal("0.10")),
    FixedCredit(Decimal("200")),
    PeakSurcharge(Decimal("500"), 18, 21),
]


@pytest.mark.parametrize("policy", ALL_POLICIES, ids=lambda p: type(p).__name__)
def test_spec_shared_contract_all_policies(policy: Policy) -> None:
    """Every policy honours the same Policy interface and purity guarantees."""
    assert isinstance(policy, Policy)
    assert isinstance(policy.name, str)
    assert policy.name

    context = QuoteContext(start_hour=12)
    amount = Decimal("1000")
    result = policy.apply(amount, context)

    assert isinstance(result, Decimal), "policy must return Decimal, never float"
    assert result == policy.apply(amount, context), "policy must be deterministic"
    assert context == QuoteContext(start_hour=12), "policy must not mutate context"
    assert amount == Decimal("1000"), "policy must not mutate its input amount"

    zero_result = policy.apply(Decimal("0"), context)
    assert isinstance(zero_result, Decimal)


def test_spec_hour_multiplier_scales_amount() -> None:
    policy = HourMultiplier(Decimal("1.5"))
    assert policy.apply(Decimal("1000"), QuoteContext(10)) == Decimal("1500")


def test_spec_percent_discount_reduces_by_percentage() -> None:
    policy = PercentDiscount(Decimal("0.10"))
    assert policy.apply(Decimal("1000"), QuoteContext(10)) == Decimal("900")


def test_spec_fixed_credit_subtracts_fixed_amount() -> None:
    policy = FixedCredit(Decimal("200"))
    assert policy.apply(Decimal("1000"), QuoteContext(10)) == Decimal("800")


def test_spec_fourth_policy_peak_surcharge_only_in_peak_hours() -> None:
    policy = PeakSurcharge(Decimal("500"), 18, 21)
    assert policy.apply(Decimal("1000"), QuoteContext(19)) == Decimal("1500")
    assert policy.apply(Decimal("1000"), QuoteContext(12)) == Decimal("1000")
    assert policy.apply(Decimal("1000"), QuoteContext(18)) == Decimal("1500")
    assert policy.apply(Decimal("1000"), QuoteContext(21)) == Decimal("1500")
    assert policy.apply(Decimal("1000"), QuoteContext(22)) == Decimal("1000")


def test_spec_fourth_policy_peak_surcharge_composes_in_engine() -> None:
    engine = QuoteEngine(
        [
            HourMultiplier(Decimal("1.5")),
            PercentDiscount(Decimal("0.10")),
            FixedCredit(Decimal("200")),
            PeakSurcharge(Decimal("500"), 18, 21),
        ]
    )
    off_peak = engine.quote(Decimal("1000"), QuoteContext(10))
    peak = engine.quote(Decimal("1000"), QuoteContext(19))
    assert off_peak.final_amount == Decimal("1150")
    assert peak.final_amount == Decimal("1650")
    assert [effect.name for effect in peak.breakdown][-1] == "PeakSurcharge"
