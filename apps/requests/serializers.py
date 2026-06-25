from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.requests.models import AssetRequest


class AssetRequestSerializer(BaseModelSerializer):
    requester_name = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta:
        model = AssetRequest
        ref_name = "EmployeeAssetRequest"
        fields = BaseModelSerializer.base_fields(
            "request_number", "requested_by", "requester_name",
            "category", "category_name", "preferred_asset",
            "reason", "priority", "status",
            "approved_by", "rejected_by",
            "approved_at", "rejected_at", "rejection_reason",
            "allocation",
        )
        read_only_fields = [
            "request_number", "status",
            "approved_by", "rejected_by",
            "approved_at", "rejected_at", "allocation",
        ]

    def get_requester_name(self, obj) -> str | None:
        if obj.requested_by:
            return obj.requested_by.get_full_name()
        return None


class AssetRequestCreateSerializer(serializers.Serializer):
    category = serializers.UUIDField(required=False, allow_null=True)
    preferred_asset = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField()
    priority = serializers.ChoiceField(
        choices=AssetRequest.Priority.choices,
        default=AssetRequest.Priority.MEDIUM,
    )


class RejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default="")
