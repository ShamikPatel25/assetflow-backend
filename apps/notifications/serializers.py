from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "recipient", "title", "message", "type",
            "payload", "is_read", "read_at", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
