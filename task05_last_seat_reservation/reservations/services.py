"""Business rules for reserving a seat under real PostgreSQL concurrency."""

from django.db import IntegrityError, transaction

from reservations.models import GymClass, Reservation

CONFLICT_STATUS = 409


class ReservationConflict(Exception):
    """A request that the HTTP layer would answer with status 409."""

    status_code = CONFLICT_STATUS


def _find_by_user_and_key(user_id: int, key: str) -> Reservation | None:
    """Find the row a repeated idempotency key must reuse."""
    return Reservation.objects.filter(user_id=user_id, key=key).first()


def _find_by_user_and_class(user_id: int, gym_class: GymClass) -> Reservation | None:
    """Find the user's existing seat for this class."""
    return Reservation.objects.filter(user_id=user_id, gym_class=gym_class).first()


def _resolve_existing(reservation: Reservation, class_id: int) -> int:
    """Return the id for a replay, or reject a key reused outside its class."""
    if reservation.gym_class_id != class_id:
        raise ReservationConflict("key was already used for a different class")
    return reservation.id


def _insert(gym_class: GymClass, user_id: int, key: str) -> int:
    """Insert with a savepoint so a unique-race can be re-read inside the transaction."""
    try:
        with transaction.atomic():
            return Reservation.objects.create(gym_class=gym_class, user_id=user_id, key=key).id
    except IntegrityError as exc:
        raced_key = _find_by_user_and_key(user_id, key)
        if raced_key is not None:
            return _resolve_existing(raced_key, gym_class.id)
        if _find_by_user_and_class(user_id, gym_class) is not None:
            raise ReservationConflict("user already reserved this class") from exc
        raise


def reserve(class_id: int, user_id: int, key: str) -> int:
    """Reserve a seat, return its id, or raise ReservationConflict for a 409.

    The class row is locked with SELECT FOR UPDATE before any user-scoped read,
    so capacity cannot be oversubscribed by concurrent workers.
    """
    with transaction.atomic():
        gym_class = GymClass.objects.select_for_update().get(pk=class_id)
        existing = _find_by_user_and_key(user_id, key)
        if existing is not None:
            return _resolve_existing(existing, class_id)
        if _find_by_user_and_class(user_id, gym_class) is not None:
            raise ReservationConflict("user already reserved this class")
        if Reservation.objects.filter(gym_class=gym_class).count() >= gym_class.capacity:
            raise ReservationConflict("class is full")
        return _insert(gym_class, user_id, key)
