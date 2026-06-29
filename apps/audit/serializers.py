from rest_framework import serializers
from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id", "actor_user", "actor_email",
            "action", "module", "object_type", "object_id", "object_repr",
            "old_data", "new_data",
            "ip_address", "user_agent", "request_id",
            "created_at",
        ]
        read_only_fields = fields
