"""Unit tests for the pure refund policy at both inclusive boundaries."""

from datetime import timedelta

from cancelapp.services import compute_refund


def test_spec_at_least_24h_returns_full_amount() -> None:
    assert compute_refund(101, timedelta(hours=24)) == 101


def test_spec_more_than_24h_returns_full_amount() -> None:
    assert compute_refund(101, timedelta(hours=25)) == 101


def test_spec_24h_plus_one_second_later_returns_half() -> None:
    remaining = timedelta(hours=24) - timedelta(seconds=1)
    assert compute_refund(101, remaining) == 50


def test_spec_exactly_2h_returns_half() -> None:
    assert compute_refund(101, timedelta(hours=2)) == 50


def test_spec_between_2h_and_24h_returns_half() -> None:
    assert compute_refund(101, timedelta(hours=23, minutes=59)) == 50


def test_spec_2h_plus_one_second_later_returns_zero() -> None:
    remaining = timedelta(hours=2) - timedelta(seconds=1)
    assert compute_refund(101, remaining) == 0


def test_spec_half_refund_rounds_down_for_odd_amount() -> None:
    assert compute_refund(1, timedelta(hours=3)) == 0
    assert compute_refund(3, timedelta(hours=3)) == 1
