"""Serializers: writable input is narrow, lifecycle fields are server-owned."""

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from transfer.models import TransferRequest
from transfer.services import (
    InvalidTransferData,
    NotAllowed,
    assert_can_create,
    create_request,
    validate_new_request,
)


class TransferRequestSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    decided_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    submitted_at = serializers.DateTimeField(read_only=True)
    decided_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = TransferRequest
        fields = [
            "id",
            "source",
            "destination",
            "item_name",
            "quantity",
            "status",
            "reason",
            "created_by",
            "decided_by",
            "created_at",
            "submitted_at",
            "decided_at",
        ]

    def validate(self, attrs):
        try:
            validate_new_request(
                source=attrs.get("source"),
                destination=attrs.get("destination"),
                quantity=attrs.get("quantity"),
            )
            assert_can_create(user=self.context["request"].user, destination=attrs["destination"])
        except InvalidTransferData as exc:
            raise serializers.ValidationError(str(exc)) from exc
        except NotAllowed as exc:
            raise PermissionDenied(str(exc)) from exc
        return attrs

    def create(self, validated_data):
        return create_request(created_by=self.context["request"].user, **validated_data)


class RejectSerializer(serializers.Serializer):
    """Payload accepted by the reject action."""

    reason = serializers.CharField(trim_whitespace=True)
