from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.licenses.models import SoftwareLicense, LicenseAssignment
from apps.employees.models import Employee


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
    """
    Read serializer for a license assignment.
    A license seat is tied to an employee (their identity / email),
    not to any specific hardware asset.
    """
    class Meta:
        model = LicenseAssignment
        fields = BaseModelSerializer.base_fields(
            "license", "employee", "assigned_by",
            "assigned_at", "revoked_at", "status",
        )
        # System-controlled: all workflow fields set by the service layer
        read_only_fields = ["assigned_by", "assigned_at", "revoked_at", "status"]

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


class AssignLicenseSerializer(serializers.Serializer):
    """
    Payload for assigning a license seat to an employee.
    Only the employee is needed — licenses follow the person,
    not the hardware they happen to be using today.
    """
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())


class RevokeLicenseSerializer(serializers.Serializer):
    assignment = serializers.UUIDField()


class BulkAssignLicenseItemSerializer(serializers.Serializer):
    """
    One item in a bulk license assignment request.
    Each item is just an employee — no asset linkage.
    """
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
