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
    license_name = serializers.CharField(source="license.name", read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = LicenseAssignment
        fields = BaseModelSerializer.base_fields(
            "license", "license_name",
            "employee", "employee_name",
            "asset", "assigned_by",
            "assigned_at", "revoked_at", "status",
        )
        read_only_fields = ["assigned_at", "revoked_at", "status"]

    def get_employee_name(self, obj) -> str | None:
        if obj.employee:
            return obj.employee.get_full_name()
        return None


class AssignLicenseSerializer(serializers.Serializer):
    employee = serializers.UUIDField()
    asset = serializers.UUIDField(required=False, allow_null=True)


class RevokeLicenseSerializer(serializers.Serializer):
    assignment = serializers.UUIDField()
