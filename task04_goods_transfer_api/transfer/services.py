"""Business rules of the request cycle, independent of the HTTP layer."""

from django.db import transaction
from django.utils import timezone

from transfer.models import Staff, TransferRequest


class TransferError(ValueError):
    """Base class for rule violations translated by the API layer."""


class InvalidTransferData(TransferError):
    """Input violates a transfer invariant."""


class NotAllowed(TransferError):
    """The actor may not perform this operation."""


class InvalidTransition(TransferError):
    """The request is not in a state that allows this operation."""


def staff_for(user) -> Staff | None:
    """Return the actor's live branch/role, or None when they have no staff profile."""
    if not user.is_authenticated:
        return None
    try:
        return Staff.objects.select_related("branch").get(user=user)
    except Staff.DoesNotExist:
        return None


def validate_new_request(*, source, destination, quantity) -> None:
    """Reject non-positive quantities and transfers inside one branch."""
    if quantity is None or quantity <= 0:
        raise InvalidTransferData("quantity must be positive")
    if source is None or destination is None or source.pk == destination.pk:
        raise InvalidTransferData("source and destination must be different branches")


def assert_can_create(*, user, destination) -> None:
    """Only a destination employee may open a request for their own branch."""
    staff = staff_for(user)
    if staff is None or staff.role != Staff.Role.EMPLOYEE or staff.branch_id != destination.pk:
        raise NotAllowed("only an employee of the destination branch may create a request")


def create_request(*, source, destination, item_name, quantity, created_by) -> TransferRequest:
    """Create a draft after checking data and creator rights."""
    validate_new_request(source=source, destination=destination, quantity=quantity)
    assert_can_create(user=created_by, destination=destination)
    return TransferRequest.objects.create(
        source=source,
        destination=destination,
        item_name=item_name,
        quantity=quantity,
        created_by=created_by,
    )


def submit_request(request: TransferRequest, user) -> TransferRequest:
    """Move an owned draft to submitted exactly once."""
    with transaction.atomic():
        locked = TransferRequest.objects.select_for_update().get(pk=request.pk)
        if locked.created_by_id != user.pk:
            raise NotAllowed("only the creator may submit this request")
        if locked.status != TransferRequest.Status.DRAFT:
            raise InvalidTransition("only a draft can be submitted")
        locked.status = TransferRequest.Status.SUBMITTED
        locked.submitted_at = timezone.now()
        locked.save(update_fields=["status", "submitted_at"])
    return locked


def decide_request(
    request: TransferRequest, user, decision: str, reason: str = ""
) -> TransferRequest:
    """Record an approve/reject decision for a submitted request once."""
    with transaction.atomic():
        locked = TransferRequest.objects.select_for_update().get(pk=request.pk)
        staff = staff_for(user)
        if (
            staff is None
            or staff.role != Staff.Role.SOURCE_MANAGER
            or staff.branch_id != locked.source_id
            or locked.created_by_id == user.pk
        ):
            raise NotAllowed("only the source manager may decide this request")
        if decision not in {"approve", "reject"}:
            raise InvalidTransferData("unknown decision")
        if decision == "reject" and not reason.strip():
            raise InvalidTransferData("a reason is required when rejecting")
        if locked.status != TransferRequest.Status.SUBMITTED:
            raise InvalidTransition("this request has already been decided")

        locked.status = (
            TransferRequest.Status.APPROVED
            if decision == "approve"
            else TransferRequest.Status.REJECTED
        )
        locked.reason = reason if decision == "reject" else ""
        locked.decided_by = user
        locked.decided_at = timezone.now()
        locked.save(update_fields=["status", "reason", "decided_by", "decided_at"])
    return locked
