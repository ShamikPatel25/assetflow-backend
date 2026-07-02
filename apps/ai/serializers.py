from rest_framework import serializers

class RiskAssessmentRequestSerializer(serializers.Serializer):
    ACTION_CHOICES = [
        ("APPROVE_REQUEST", "Approve Asset Request"),
        ("ALLOCATE_ASSET", "Allocate Asset Manually"),
    ]
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    
    # Context IDs
    request_id = serializers.UUIDField(required=False, allow_null=True, help_text="Required if action is APPROVE_REQUEST")
    employee_id = serializers.UUIDField(required=False, allow_null=True, help_text="Required if action is ALLOCATE_ASSET")
    asset_id = serializers.UUIDField(required=False, allow_null=True, help_text="Required if action is ALLOCATE_ASSET")

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        for field in ["request_id", "employee_id", "asset_id"]:
            if field in data and data[field] == "":
                data[field] = None
        return super().to_internal_value(data)

    def validate(self, data):
        action = data.get("action")
        if action == "APPROVE_REQUEST":
            if not data.get("request_id"):
                raise serializers.ValidationError({"request_id": "This field is required for APPROVE_REQUEST."})
        elif action == "ALLOCATE_ASSET":
            if not data.get("employee_id") or not data.get("asset_id"):
                raise serializers.ValidationError("Both employee_id and asset_id are required for ALLOCATE_ASSET.")
        return data

class RiskAssessmentResponseSerializer(serializers.Serializer):
    risk_score = serializers.IntegerField(min_value=0, max_value=100)
    risk_level = serializers.ChoiceField(choices=["LOW", "MEDIUM", "HIGH"])
    recommendation = serializers.ChoiceField(choices=["APPROVE", "REVIEW", "DENY"])
    reasoning = serializers.CharField()
