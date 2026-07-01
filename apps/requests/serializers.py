from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.requests.models import AssetRequest
from apps.assets.models import Asset


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


    def validate_preferred_asset(self, value):
        if value:
            try:
                asset = Asset.objects.get(pk=value)
                if asset.status != Asset.Status.AVAILABLE:
                    raise serializers.ValidationError(f"This asset is currently {asset.status.lower()} and cannot be requested.")
            except Asset.DoesNotExist:
                pass
        return value

    def validate(self, attrs):
        category_id = attrs.get("category")
        preferred_asset_id = attrs.get("preferred_asset")

        if category_id and preferred_asset_id:
            try:
                asset = Asset.objects.get(pk=preferred_asset_id)
                if str(asset.category_id) != str(category_id):
                    raise serializers.ValidationError({
                        "preferred_asset": "The preferred asset does not belong to the requested category."
                    })
            except Asset.DoesNotExist:
                pass
        
        return super().validate(attrs)

class RejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default="")

class ApproveSerializer(serializers.Serializer):
    asset = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
