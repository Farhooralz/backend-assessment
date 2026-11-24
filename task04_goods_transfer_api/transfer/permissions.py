"""Action-level authorization; row visibility is enforced by the viewset queryset."""

from rest_framework.permissions import BasePermission

from transfer.models import Staff
from transfer.services import staff_for


class TransferActionPermission(BasePermission):
    """Grant action rights by live staff role, then by object ownership/source."""

    def has_permission(self, request, view) -> bool:
        staff = staff_for(request.user)
        if staff is None:
            return False
        # Object actions check the role after get_object(), so an out-of-scope
        # record stays a 404 instead of being reported as a 403.
        return view.action != "create" or staff.role == Staff.Role.EMPLOYEE

    def has_object_permission(self, request, view, obj) -> bool:
        staff = staff_for(request.user)
        if staff is None:
            return False
        if view.action == "submit":
            return staff.role == Staff.Role.EMPLOYEE and obj.created_by_id == request.user.pk
        if view.action in {"approve", "reject"}:
            return staff.role == Staff.Role.SOURCE_MANAGER and staff.branch_id == obj.source_id
        return True
