from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.permissions import IsOrganizationAdmin
from apps.base.views import ReadOnlyViewSet
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer


@extend_schema_view(
    list=extend_schema(tags=["Audit Logs"]),
    retrieve=extend_schema(tags=["Audit Logs"]),
)
class AuditLogViewSet(ReadOnlyViewSet):
    """Read-only audit log listing. Only Org Admin can view."""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]
    search_fields = ["action", "module", "actor_email", "object_repr"]
    ordering_fields = ["created_at", "module", "action"]
    filterset_fields = ["module", "action", "actor_user"]
