"""ViewSet exposing the request lifecycle; business rules live in services."""

from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from transfer.exceptions import Conflict
from transfer.models import Staff, TransferRequest
from transfer.permissions import TransferActionPermission
from transfer.serializers import RejectSerializer, TransferRequestSerializer
from transfer.services import (
    InvalidTransferData,
    InvalidTransition,
    NotAllowed,
    decide_request,
    staff_for,
    submit_request,
)


class TransferPagination(PageNumberPagination):
    """Small pages make the stable ordering easy to observe."""

    page_size = 2
    page_size_query_param = "page_size"
    max_page_size = 100


class TransferRequestViewSet(ModelViewSet):
    serializer_class = TransferRequestSerializer
    # Basic comes first so anonymous requests get a 401 with WWW-Authenticate.
    authentication_classes = [BasicAuthentication, SessionAuthentication]
    permission_classes = [TransferActionPermission]
    pagination_class = TransferPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        staff = staff_for(self.request.user)
        if staff is None:
            return TransferRequest.objects.none()

        if staff.role == Staff.Role.SOURCE_MANAGER:
            # "Sent" covers submitted plus decided requests, so a second decision
            # is a 409 conflict rather than a 404 on a vanished object.
            queryset = TransferRequest.objects.filter(source_id=staff.branch_id).exclude(
                status=TransferRequest.Status.DRAFT
            )
        else:
            queryset = TransferRequest.objects.filter(destination_id=staff.branch_id)

        status = self.request.query_params.get("status")
        if status:
            if status not in TransferRequest.Status.values:
                raise ValidationError({"status": "unknown status"})
            queryset = queryset.filter(status=status)
        return queryset.select_related(
            "source", "destination", "created_by", "decided_by"
        ).order_by("-created_at", "-id")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        obj = self.get_object()
        try:
            obj = submit_request(obj, request.user)
        except NotAllowed as exc:
            raise PermissionDenied(str(exc)) from exc
        except InvalidTransition as exc:
            raise Conflict(str(exc)) from exc
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, "approve")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, "reject")

    def _decide(self, request, decision: str) -> Response:
        obj = self.get_object()
        reason = ""
        if decision == "reject":
            payload = RejectSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            reason = payload.validated_data["reason"]
        try:
            obj = decide_request(obj, request.user, decision, reason)
        except InvalidTransition as exc:
            raise Conflict(str(exc)) from exc
        except InvalidTransferData as exc:
            raise ValidationError(str(exc)) from exc
        except NotAllowed as exc:
            raise PermissionDenied(str(exc)) from exc
        return Response(self.get_serializer(obj).data)
