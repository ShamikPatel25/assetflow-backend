from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.assets.models import AssetCategory, Asset


class AssetCategorySerializer(BaseModelSerializer):

    class Meta:
        model = AssetCategory
        fields = BaseModelSerializer.base_fields(
            "name", "code", "description", "category_type",
            "parent",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.parent:
            data["parent"] = {
                "id": str(instance.parent_id),
                "name": instance.parent.name
            }
        return data

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

    class Meta:
        model = Asset
        ref_name = "Asset"
        fields = BaseModelSerializer.base_fields(
            "asset_code", "category",
            "name", "brand", "model", "serial_number",
            "purchase_date", "warranty_expiry_date",
            "purchase_cost", "currency",
            "status", "condition",
            "current_owner", "current_allocation",
            "metadata",
        )
        read_only_fields = ["current_owner", "current_allocation"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.category:
            data["category"] = {
                "id": str(instance.category_id),
                "name": instance.category.name
            }
        if instance.current_owner:
            data["current_owner"] = {
                "id": str(instance.current_owner_id),
                "name": instance.current_owner.get_full_name()
            }
        if instance.current_allocation:
            data["current_allocation"] = {
                "id": str(instance.current_allocation_id)
            }
            
        # Format empty metadata as null
        if not data.get("metadata"):
            data["metadata"] = None
            
        return data

    def validate(self, attrs):
        purchase_date = attrs.get("purchase_date", self.instance.purchase_date if self.instance else None)
        warranty_date = attrs.get("warranty_expiry_date", self.instance.warranty_expiry_date if self.instance else None)

        if purchase_date and warranty_date and warranty_date < purchase_date:
            raise serializers.ValidationError({
                "warranty_expiry_date": "Warranty expiry date cannot be earlier than the purchase date."
            })
            
        serial_number = attrs.get("serial_number", self.instance.serial_number if self.instance else None)
        if serial_number:
            qs = Asset.objects.filter(serial_number=serial_number)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "serial_number": f"An asset with serial number '{serial_number}' already exists."
                })
            
        return super().validate(attrs)
