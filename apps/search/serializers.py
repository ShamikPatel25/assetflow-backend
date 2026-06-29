from rest_framework import serializers

class SearchResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(required=False, allow_null=True)
    url = serializers.CharField(required=False, allow_null=True)

class GlobalSearchResponseSerializer(serializers.Serializer):
    results = SearchResultSerializer(many=True)
