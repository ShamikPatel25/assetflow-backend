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

    def validate_parent(self, value):
        if value is not None:
            # 1. The selected parent cannot itself be a sub-category.
            if value.parent is not None:
                raise serializers.ValidationError("Only 1 level of sub-categories is supported. You cannot select a sub-category as a parent.")
            # 2. If this category already has sub-categories, it cannot become a sub-category itself.
            if self.instance and self.instance.children.filter(is_deleted=False).exists():
                raise serializers.ValidationError("This category already has sub-categories. It cannot be nested under another category.")
        return value

    def validate(self, attrs):
        parent = attrs.get("parent", self.instance.parent if self.instance else None)
        category_type = attrs.get("category_type", self.instance.category_type if self.instance else None)
        
        if parent and category_type and parent.category_type != category_type:
            raise serializers.ValidationError({
                "category_type": f"Sub-category type '{category_type}' must match parent category type '{parent.category_type}'."
            })
            
        return super().validate(attrs)


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
