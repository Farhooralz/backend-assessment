"""Concurrency test: two cancels of the same row must agree on one refund."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from django.db import connections
from django.test import TransactionTestCase

from cancelapp.models import Branch, RefundDocument, Reservation, User
from cancelapp.services import CancellationResult, cancel

START = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


class TestConcurrentCancel(TransactionTestCase):
    """Real PostgreSQL: independent connections race for the same reservation."""

    def test_spec_concurrent_cancels_produce_one_refund_and_same_result(self) -> None:
        branch = Branch.objects.create(name="North")
        owner = User.objects.create(name="owner", branch=branch)
        reservation = Reservation.objects.create(
            owner=owner,
            branch=branch,
            start=START,
            payment_amount=101,
            status="confirmed",
        )
        now = START - timedelta(hours=25)
        barrier = threading.Barrier(2)
        results: list[CancellationResult] = []
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                # Both callers read "confirmed" before either one cancels.
                fresh = Reservation.objects.get(pk=reservation.pk)
                fresh_owner = User.objects.get(pk=owner.pk)
                barrier.wait(timeout=8)
                results.append(cancel(fresh, fresh_owner, now))
            except BaseException as error:
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not any(thread.is_alive() for thread in threads), "a worker thread hung"
        assert not errors, f"unexpected worker errors: {errors!r}"
        assert len(results) == 2
        assert results[0] == results[1] == CancellationResult(refund_amount=101)
        reservation.refresh_from_db()
        assert reservation.status == "cancelled"
        assert RefundDocument.objects.filter(reservation=reservation).count() == 1
