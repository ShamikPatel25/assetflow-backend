from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.incidents.models import Incident, RepairRecord


class IncidentSerializer(BaseModelSerializer):
    reporter_name = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True, default=None)

    class Meta:
        model = Incident
        fields = BaseModelSerializer.base_fields(
            "incident_number", "asset", "asset_code",
            "reported_by", "reporter_name",
            "assigned_to", "assignee_name",
            "title", "description", "category", "priority", "status",
            "ai_category", "ai_summary", "ai_confidence", "ai_model_version",
            "opened_at", "resolved_at", "closed_at",
        )
        read_only_fields = [
            "incident_number", "opened_at", "status",
            "resolved_at", "closed_at",
            "ai_category", "ai_summary", "ai_confidence", "ai_model_version",
        ]

    def get_reporter_name(self, obj) -> str | None:
        if obj.reported_by:
            return obj.reported_by.get_full_name()
        return None

    def get_assignee_name(self, obj) -> str | None:
        if obj.assigned_to:
            return obj.assigned_to.get_full_name()
        return None


class RepairRecordSerializer(BaseModelSerializer):
    incident_number = serializers.CharField(
        source="incident.incident_number", read_only=True
    )
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)

    class Meta:
        model = RepairRecord
        fields = BaseModelSerializer.base_fields(
            "incident", "incident_number", "asset", "asset_code",
            "vendor_name", "repair_cost", "currency",
            "repair_start_date", "repair_end_date", "remarks",
        )
