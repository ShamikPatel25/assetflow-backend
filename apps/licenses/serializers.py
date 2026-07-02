from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.licenses.models import SoftwareLicense, LicenseAssignment


class SoftwareLicenseSerializer(BaseModelSerializer):
    used_seats = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)

    class Meta:
        model = SoftwareLicense
        fields = BaseModelSerializer.base_fields(
            "name", "vendor", "license_key", "license_type",
            "total_seats", "used_seats", "available_seats",
            "purchase_date", "expiry_date",
            "cost", "currency", "status", "metadata",
        )


class LicenseAssignmentSerializer(BaseModelSerializer):
    class Meta:
        model = LicenseAssignment
        fields = BaseModelSerializer.base_fields(
            "license", "employee", "asset", "assigned_by",
            "assigned_at", "revoked_at", "status",
        )
        read_only_fields = ["assigned_at", "revoked_at", "status"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.license:
            data["license"] = {
                "id": instance.license_id,
                "name": instance.license.name
            }
        if instance.employee:
            data["employee"] = {
                "id": instance.employee_id,
                "name": instance.employee.get_full_name()
            }
        if getattr(instance, "assigned_by", None):
            data["assigned_by"] = {
                "id": instance.assigned_by_id,
                "name": instance.assigned_by.get_full_name()
            }
        return data


from apps.employees.models import Employee
from apps.assets.models import Asset

class AssignLicenseSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.all(), required=False, allow_null=True)

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        if "asset" in data and data["asset"] == "":
            data["asset"] = None
        return super().to_internal_value(data)


class RevokeLicenseSerializer(serializers.Serializer):
    assignment = serializers.UUIDField()
