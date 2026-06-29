from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins
from rest_framework import serializers as drf_serializers
from drf_spectacular.utils import extend_schema_view, extend_schema, inline_serializer

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


@extend_schema_view(
    list=extend_schema(tags=["Notifications"]),
    retrieve=extend_schema(tags=["Notifications"]),
    mark_all_read=extend_schema(
        tags=["Notifications"],
        summary="Mark All Notifications as Read",
        request=None,
        responses={200: inline_serializer("MarkAllReadResponse", {"marked": drf_serializers.IntegerField()})},
    ),
    mark_read=extend_schema(
        tags=["Notifications"],
        summary="Mark Single Notification as Read",
        request=None,
        responses={200: NotificationSerializer},
    ),
)
class NotificationViewSet(
    GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """
    GET  /api/v1/notifications/              -> list my notifications
    GET  /api/v1/notifications/{id}/         -> detail
    POST /api/v1/notifications/mark-read/    -> mark all as read
    POST /api/v1/notifications/{id}/read/    -> mark one as read
    """

    http_method_names = ["get", "post"]
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_all_read(self, request):
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({"marked": count})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at"])
        return Response(NotificationSerializer(notification).data)
