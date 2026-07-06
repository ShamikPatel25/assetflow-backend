from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.requests.models import AssetRequest
from apps.assets.models import Asset


class AssetRequestSerializer(BaseModelSerializer):

    class Meta:
        model = AssetRequest
        ref_name = "EmployeeAssetRequest"
        fields = BaseModelSerializer.base_fields(
            "request_number", "requested_by",
            "category", "preferred_asset",
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.requested_by:
            data["requested_by"] = {
                "id": str(instance.requested_by_id),
                "name": instance.requested_by.get_full_name()
            }
        if instance.category:
            data["category"] = {
                "id": str(instance.category_id),
                "name": instance.category.name
            }
        if instance.preferred_asset:
            data["preferred_asset"] = {
                "id": str(instance.preferred_asset_id),
                "name": instance.preferred_asset.name
            }
        if getattr(instance, "approved_by", None):
            data["approved_by"] = {
                "id": str(instance.approved_by_id),
                "name": instance.approved_by.get_full_name()
            }
        else:
            data["approved_by"] = None
        if getattr(instance, "rejected_by", None):
            data["rejected_by"] = {
                "id": str(instance.rejected_by_id),
                "name": instance.rejected_by.get_full_name()
            }
        else:
            data["rejected_by"] = None
        return data


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

class BulkApproveSerializer(serializers.Serializer):
    request_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

class BulkRejectSerializer(serializers.Serializer):
    request_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False
    )
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default="")
