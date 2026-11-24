"""Service-level regression tests for per-request staff lookup."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from transfer.services import staff_for

pytestmark = pytest.mark.django_db


def test_spec_staff_for_is_cached_per_request(employee, other_manager) -> None:
    with CaptureQueriesContext(connection) as first_context:
        first = staff_for(employee)
        second = staff_for(employee)
    assert first is not None and second is not None
    assert first.pk == second.pk
    assert len(first_context.captured_queries) == 1

    with CaptureQueriesContext(connection) as second_context:
        other = staff_for(other_manager)
    assert other is not None and other.pk != first.pk
    assert len(second_context.captured_queries) == 1
