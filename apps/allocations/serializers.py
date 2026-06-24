from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.allocations.models import AssetAllocation


class AssetAllocationSerializer(BaseModelSerializer):
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    employee_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AssetAllocation
        fields = BaseModelSerializer.base_fields(
            "allocation_number", "asset", "asset_code", "asset_name",
            "employee", "employee_name", "assigned_by", "assigned_by_name",
            "allocated_at", "expected_return_date", "returned_at",
            "return_condition", "remarks", "status",
        )
        read_only_fields = ["allocation_number", "status", "returned_at", "assigned_by"]

    def get_employee_name(self, obj) -> str | None:
        if obj.employee:
            return obj.employee.get_full_name()
        return None

    def get_assigned_by_name(self, obj) -> str | None:
        if obj.assigned_by:
            return obj.assigned_by.get_full_name()
        return None


class AllocateSerializer(serializers.Serializer):
    asset = serializers.UUIDField()
    employee = serializers.UUIDField()
    expected_return_date = serializers.DateField(required=False, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True)


class ReturnSerializer(serializers.Serializer):
    return_condition = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)
