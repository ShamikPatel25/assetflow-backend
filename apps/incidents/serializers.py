from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer, FlexibleDateField
from apps.incidents.models import Incident, RepairRecord


class IncidentSerializer(BaseModelSerializer):
    class Meta:
        model = Incident
        fields = BaseModelSerializer.base_fields(
            "incident_number", "asset", 
            "reported_by", 
            "assigned_to", 
            "title", "description", "category", "priority", "status",
            "opened_at", "resolved_at", "closed_at",
        )
        read_only_fields = [
            "incident_number", "opened_at", "status",
            "resolved_at", "closed_at",
        ]
        extra_kwargs = {
            "reported_by": {"required": False, "allow_null": True}
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        if instance.asset:
            data["asset"] = {
                "id": instance.asset_id,
                "asset_code": instance.asset.asset_code,
            }
            
        if instance.reported_by:
            data["reported_by"] = {
                "id": instance.reported_by_id,
                "name": instance.reported_by.get_full_name()
            }
            
        if instance.assigned_to:
            data["assigned_to"] = {
                "id": instance.assigned_to_id,
                "name": instance.assigned_to.get_full_name()
            }
            
        return data

    def validate(self, data):
        request = self.context.get("request")
        if request and hasattr(request, "user") and getattr(request.user, "role", None) == "EMPLOYEE":
            employee = getattr(request.user, "employee_profile", None)
            
            reported_by = data.get("reported_by")
            if reported_by and employee and reported_by != employee:
                raise serializers.ValidationError({"reported_by": "You can only report an incident for yourself."})
            
            asset = data.get("asset")
            if asset and employee and asset.current_owner != employee:
                raise serializers.ValidationError({"asset": "You can only report an incident for an asset that is currently allocated to you."})
                
        return data


class IncidentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Incident.Status.choices)


class BulkIncidentStatusUpdateSerializer(serializers.Serializer):
    incident_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False
    )
    status = serializers.ChoiceField(choices=Incident.Status.choices)


class RepairRecordSerializer(BaseModelSerializer):
    repair_start_date = FlexibleDateField(required=False, allow_null=True, default=None)
    repair_end_date = FlexibleDateField(required=False, allow_null=True, default=None)

    class Meta:
        model = RepairRecord
        fields = BaseModelSerializer.base_fields(
            "incident", "asset",
            "vendor_name", "repair_cost", "currency",
            "repair_start_date", "repair_end_date", "remarks",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        if instance.incident:
            data["incident"] = {
                "id": instance.incident_id,
                "incident_number": instance.incident.incident_number,
            }
            
        if instance.asset:
            data["asset"] = {
                "id": instance.asset_id,
                "asset_code": instance.asset.asset_code,
            }
            
        return data
