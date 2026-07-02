from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer, FlexibleDateField
from apps.allocations.models import AssetAllocation


class AssetAllocationSerializer(BaseModelSerializer):
    expected_return_date = FlexibleDateField(required=False, allow_null=True, default=None)

    class Meta:
        model = AssetAllocation
        fields = BaseModelSerializer.base_fields(
            "allocation_number", "asset",
            "employee", "assigned_by",
            "allocated_at", "expected_return_date", "returned_at",
            "return_condition", "remarks", "status",
        )
        read_only_fields = ["allocation_number", "status", "returned_at", "assigned_by"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.asset:
            data["asset"] = {
                "id": instance.asset_id,
                "asset_code": instance.asset.asset_code,
                "name": instance.asset.name
            }
        if instance.employee:
            data["employee"] = {
                "id": instance.employee_id,
                "name": instance.employee.get_full_name()
            }
        if instance.assigned_by:
            data["assigned_by"] = {
                "id": instance.assigned_by_id,
                "name": instance.assigned_by.get_full_name()
            }
        return data


from apps.assets.models import Asset
from apps.employees.models import Employee

class AllocateSerializer(serializers.Serializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.all())
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    expected_return_date = FlexibleDateField(required=False, allow_null=True, default=None)
    remarks = serializers.CharField(required=False, allow_blank=True)


class ReturnSerializer(serializers.Serializer):
    return_condition = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)
