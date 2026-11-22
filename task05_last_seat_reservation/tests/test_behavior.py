"""Spec behaviour: idempotency, 409 conflicts, rollback and database constraints."""

import pytest
from django.db import IntegrityError, transaction

from reservations import services
from reservations.models import GymClass, Reservation
from reservations.services import ReservationConflict, reserve


@pytest.mark.django_db
def test_spec_repeat_same_key_same_class_returns_same_id() -> None:
    """A repeated successful request returns the same reservation id."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    first_id = reserve(klass.id, user_id=1, key="key-1")
    assert reserve(klass.id, user_id=1, key="key-1") == first_id
    assert Reservation.objects.count() == 1


@pytest.mark.django_db
def test_spec_same_key_other_class_conflict_409() -> None:
    """A key that succeeded for one class cannot be reused for another class."""
    first = GymClass.objects.create(name="Yoga", capacity=3)
    other = GymClass.objects.create(name="Pilates", capacity=3)
    reserve(first.id, user_id=1, key="shared-key")
    with pytest.raises(ReservationConflict) as exc:
        reserve(other.id, user_id=1, key="shared-key")
    assert exc.value.status_code == 409
    assert Reservation.objects.count() == 1


@pytest.mark.django_db
def test_spec_full_capacity_conflict_409() -> None:
    """A fourth user cannot take a seat in a class with capacity 3."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    for user_id in (1, 2, 3):
        reserve(klass.id, user_id=user_id, key=f"key-{user_id}")
    with pytest.raises(ReservationConflict) as exc:
        reserve(klass.id, user_id=4, key="key-4")
    assert exc.value.status_code == 409
    assert Reservation.objects.filter(gym_class=klass).count() == 3


@pytest.mark.django_db
def test_spec_repeat_reservation_new_key_conflict_409() -> None:
    """A user already holding a seat cannot reserve the same class with a new key."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    original_id = reserve(klass.id, user_id=1, key="key-1")
    with pytest.raises(ReservationConflict) as exc:
        reserve(klass.id, user_id=1, key="key-2")
    assert exc.value.status_code == 409
    assert Reservation.objects.count() == 1
    assert Reservation.objects.get(pk=original_id).key == "key-1"


@pytest.mark.django_db
def test_spec_failure_mid_operation_does_not_consume_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An injected failure after the insert rolls the transaction back completely."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    real_create = Reservation.objects.create
    calls = 0

    def failing_create(*args: object, **kwargs: object) -> Reservation:
        nonlocal calls
        calls += 1
        created = real_create(*args, **kwargs)
        if calls == 1:
            raise RuntimeError("injected failure after insert")
        return created

    with monkeypatch.context() as mp:
        mp.setattr(Reservation.objects, "create", failing_create)
        with pytest.raises(RuntimeError, match="injected failure after insert"):
            reserve(klass.id, user_id=1, key="key-1")

    assert Reservation.objects.count() == 0
    assert reserve(klass.id, user_id=1, key="key-1") > 0
    assert Reservation.objects.filter(gym_class=klass).count() == 1


@pytest.mark.django_db
def test_spec_unique_user_class_constraint() -> None:
    """The database rejects a second reservation for the same user and class."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    Reservation.objects.create(gym_class=klass, user_id=1, key="key-1")
    with pytest.raises(IntegrityError), transaction.atomic():
        Reservation.objects.create(gym_class=klass, user_id=1, key="key-2")


@pytest.mark.django_db
def test_spec_unique_user_key_constraint() -> None:
    """The database rejects a user's key being reused for a different class."""
    first = GymClass.objects.create(name="Yoga", capacity=3)
    other = GymClass.objects.create(name="Pilates", capacity=3)
    Reservation.objects.create(gym_class=first, user_id=1, key="shared-key")
    with pytest.raises(IntegrityError), transaction.atomic():
        Reservation.objects.create(gym_class=other, user_id=1, key="shared-key")


@pytest.mark.django_db
def test_spec_integrity_error_rereads_shared_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """An IntegrityError race resolves by re-reading the winning row's id."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    existing = Reservation.objects.create(gym_class=klass, user_id=1, key="key-1")
    real_find_key = services._find_by_user_and_key
    real_find_class = services._find_by_user_and_class
    key_lookups = 0
    class_lookups = 0

    def hidden_key_once(user_id: int, key: str) -> Reservation | None:
        nonlocal key_lookups
        key_lookups += 1
        if key_lookups == 1:
            return None
        return real_find_key(user_id, key)

    def hidden_class_once(user_id: int, gym_class: GymClass) -> Reservation | None:
        nonlocal class_lookups
        class_lookups += 1
        if class_lookups == 1:
            return None
        return real_find_class(user_id, gym_class)

    def raising_create(*args: object, **kwargs: object) -> Reservation:
        raise IntegrityError("simulated concurrent insert")

    with monkeypatch.context() as mp:
        mp.setattr(services, "_find_by_user_and_key", hidden_key_once)
        mp.setattr(services, "_find_by_user_and_class", hidden_class_once)
        mp.setattr(Reservation.objects, "create", raising_create)
        assert reserve(klass.id, user_id=1, key="key-1") == existing.pk

    assert key_lookups == 2
    assert Reservation.objects.count() == 1
