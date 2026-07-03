import uuid

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.errors import AFValidationError, error_codes
from apps.base.permissions import IsOrgAdminOrHR, IsOrgAdminOrHROrReadOnly
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
        user = self.request.user
        employee = getattr(user, "employee_profile", None)
        
        asset = serializer.validated_data.get("asset")
        incident_category = serializer.validated_data.get("category")
        
        if asset and incident_category:
            from apps.assets.models import AssetCategory
            from apps.incidents.models import Incident
            asset_type = asset.category.category_type
            if asset_type in (AssetCategory.CategoryType.SOFTWARE, AssetCategory.CategoryType.LICENSE):
                if incident_category in (Incident.Category.HARDWARE, Incident.Category.PHYSICAL_DAMAGE):
                    raise AFValidationError(f"Cannot report a {incident_category.replace('_', ' ').title()} incident for a {asset_type.title()} asset.")

        if getattr(user, "role", "EMPLOYEE") == "EMPLOYEE":
            requested_reported_by = serializer.validated_data.get("reported_by")
            if requested_reported_by and requested_reported_by != employee:
                raise AFValidationError("You can only report incidents for yourself and your own assigned assets.")
            
            reported_by = employee
            asset = serializer.validated_data.get("asset")
            if asset:
                from apps.allocations.models import AssetAllocation
                is_allocated = AssetAllocation.objects.filter(
                    asset=asset,
                    employee=employee,
                    status=AssetAllocation.Status.ACTIVE
                ).exists()
                if not is_allocated:
                    raise AFValidationError("You can only report incidents for assets currently assigned to you.")
        else:
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
                "Only open or in-progress incidents can be resolved."
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
                "Only resolved incidents can be closed."
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
    permission_classes = [IsAuthenticated, IsOrgAdminOrHROrReadOnly]
    search_fields = ["vendor_name", "incident__incident_number"]
    filterset_fields = ["incident", "asset"]

    def perform_create(self, serializer):
        incident = serializer.validated_data.get("incident")
        if incident and incident.status == Incident.Status.CLOSED:
            raise AFValidationError("Cannot add repair records to a closed incident.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        incident = serializer.instance.incident
        if incident and incident.status == Incident.Status.CLOSED:
            raise AFValidationError("Cannot update repair records for a closed incident.")
        
        new_incident = serializer.validated_data.get("incident")
        if new_incident and new_incident.status == Incident.Status.CLOSED:
            raise AFValidationError("Cannot move a repair record to a closed incident.")
            
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.incident.status == Incident.Status.CLOSED:
            raise AFValidationError("Cannot delete repair records from a closed incident.")
        super().perform_destroy(instance)
