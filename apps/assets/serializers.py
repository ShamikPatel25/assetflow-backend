from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.assets.models import AssetCategory, Asset


class AssetCategorySerializer(BaseModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = AssetCategory
        fields = BaseModelSerializer.base_fields(
            "name", "code", "description", "category_type",
            "parent", "parent_name",
        )


class AssetSerializer(BaseModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        ref_name = "Asset"
        fields = BaseModelSerializer.base_fields(
            "asset_code", "category", "category_name",
            "name", "brand", "model", "serial_number",
            "purchase_date", "warranty_expiry_date",
            "purchase_cost", "currency",
            "status", "condition",
            "current_owner", "owner_name", "current_allocation",
            "metadata",
        )
        read_only_fields = ["current_owner", "current_allocation"]

    def get_owner_name(self, obj) -> str | None:
        if obj.current_owner:
            return obj.current_owner.get_full_name()
        return None


class AssetMinimalSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns and references."""

    class Meta:
        model = Asset
        fields = ["id", "asset_code", "name", "status"]
