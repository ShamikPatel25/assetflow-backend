import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.errors import AFValidationError, error_codes
from apps.base.permissions import IsOrgAdminOrReadOnly, IsOrgAdminOrHR
from apps.base.views import CRUDViewSet
from apps.incidents.models import Incident, RepairRecord
from apps.incidents.serializers import IncidentSerializer, RepairRecordSerializer
from apps.notifications.services import NotificationService


@extend_schema_view(
    list=extend_schema(tags=["Incidents"]),
    create=extend_schema(tags=["Incidents"]),
    retrieve=extend_schema(tags=["Incidents"]),
    update=extend_schema(tags=["Incidents"]),
    partial_update=extend_schema(tags=["Incidents"]),
    destroy=extend_schema(tags=["Incidents"]),
    resolve=extend_schema(
        tags=["Incidents"],
        summary="Resolve Incident",
        request=None,
        responses={200: IncidentSerializer},
    ),
    close=extend_schema(
        tags=["Incidents"],
        summary="Close Incident",
        request=None,
        responses={200: IncidentSerializer},
    ),
)
class IncidentViewSet(CRUDViewSet):
    """
    Incident management with status transitions.
    POST   /api/v1/incidents/{id}/resolve/   -> resolve
    POST   /api/v1/incidents/{id}/close/     -> close
    """

    queryset = Incident.objects.select_related("asset", "reported_by", "assigned_to")
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["incident_number", "title", "description"]
    ordering_fields = ["created_at", "priority", "status", "opened_at"]
    filterset_fields = ["status", "category", "priority", "asset", "reported_by"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "role", None) == "EMPLOYEE":
            employee = getattr(user, "employee_profile", None)
            if employee:
                return qs.filter(reported_by=employee)
            return qs.none()
        return qs

    def perform_create(self, serializer):
        employee = getattr(self.request.user, "employee_profile", None)
        reported_by = serializer.validated_data.get("reported_by") or employee
        if not reported_by:
            raise AFValidationError("You must have an employee profile to report an incident.")
        
        instance = serializer.save(
            incident_number=f"INC-{uuid.uuid4().hex[:8].upper()}",
            created_by=self.request.user,
            reported_by=reported_by
        )

        NotificationService.notify_incident_reported(instance)

    def perform_update(self, serializer):
        incident = self.get_object()
        if incident.status in (Incident.Status.RESOLVED, Incident.Status.CLOSED):
            raise AFValidationError(
                "Cannot update a resolved or closed incident.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )
        super().perform_update(serializer)

        NotificationService.notify_incident_updated(incident)

    @action(detail=True, methods=["post"], url_path="resolve",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def resolve(self, request, pk=None):
        incident = self.get_object()
        if incident.status not in (Incident.Status.OPEN, Incident.Status.IN_PROGRESS):
            raise AFValidationError(
                "Only open or in-progress incidents can be resolved.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )
        incident.status = Incident.Status.RESOLVED
        incident.resolved_at = timezone.now()
        incident.save(update_fields=["status", "resolved_at", "updated_at"])

        NotificationService.notify_incident_updated(incident)

        return Response(IncidentSerializer(incident).data)

    @action(detail=True, methods=["post"], url_path="close",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def close(self, request, pk=None):
        incident = self.get_object()
        if incident.status != Incident.Status.RESOLVED:
            raise AFValidationError(
                "Only resolved incidents can be closed.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )
        incident.status = Incident.Status.CLOSED
        incident.closed_at = timezone.now()
        incident.save(update_fields=["status", "closed_at", "updated_at"])

        NotificationService.notify_incident_updated(incident)

        return Response(IncidentSerializer(incident).data)


@extend_schema_view(
    list=extend_schema(tags=["Incidents"]),
    create=extend_schema(tags=["Incidents"]),
    retrieve=extend_schema(tags=["Incidents"]),
    update=extend_schema(tags=["Incidents"]),
    partial_update=extend_schema(tags=["Incidents"]),
    destroy=extend_schema(tags=["Incidents"]),
)
class RepairRecordViewSet(CRUDViewSet):
    """CRUD for repair records linked to incidents."""

    queryset = RepairRecord.objects.select_related("incident", "asset")
    serializer_class = RepairRecordSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrReadOnly]
    search_fields = ["vendor_name", "incident__incident_number"]
    filterset_fields = ["incident", "asset"]
