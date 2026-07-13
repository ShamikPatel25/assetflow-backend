from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema

from django.conf import settings
from apps.base.errors import AFValidationError, error_codes
from apps.base.permissions import IsOrgAdminOrHROrReadOnly
from apps.base.utils import generate_reference_number
from apps.base.views import CRUDViewSet
from apps.incidents.models import Incident, RepairRecord
from apps.incidents.serializers import (
    IncidentSerializer, 
    IncidentStatusUpdateSerializer, 
    BulkIncidentStatusUpdateSerializer,
    RepairRecordSerializer
)
from apps.notifications.services import NotificationService


@extend_schema_view(
    list=extend_schema(tags=["Incidents"]),
    create=extend_schema(tags=["Incidents"]),
    retrieve=extend_schema(tags=["Incidents"]),
    update=extend_schema(tags=["Incidents"]),
    partial_update=extend_schema(tags=["Incidents"]),
    destroy=extend_schema(tags=["Incidents"]),
    change_status=extend_schema(
        tags=["Incidents"],
        summary="Change Incident Status",
        request=IncidentStatusUpdateSerializer,
        responses={200: IncidentSerializer},
    ),
    bulk_status_update=extend_schema(
        tags=["Incidents"],
        summary="Bulk Change Incident Statuses",
        request=BulkIncidentStatusUpdateSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "updated_count": {"type": "integer"},
                    "errors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "error": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
    ),
)
class IncidentViewSet(CRUDViewSet):
    """
    Incident management with status transitions.
    POST  /api/v1/incidents/{id}/status/    -> change status
    POST  /api/v1/incidents/bulk-status/    -> bulk change status
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

    @staticmethod
    def _apply_incident_status_transition(incident, new_status, role, employee_profile):
        """
        Validate and apply a single incident status transition.

        Encodes the state-machine rules shared by change_status and
        bulk_status_update so the logic is never duplicated.

        Returns:
            None on success.

        Raises:
            AFValidationError: when the transition is not permitted.
        """
        current_status = incident.status

        if current_status in (Incident.Status.RESOLVED, Incident.Status.CLOSED):
            raise AFValidationError(
                f"Cannot change status of a {current_status.lower()} incident."
            )

        if new_status == current_status:
            return  # no-op, caller handles this case

        if role == "EMPLOYEE":
            if incident.reported_by != employee_profile:
                raise AFValidationError(
                    "You do not have permission to change the status of this incident."
                )
            if current_status != Incident.Status.OPEN or new_status != Incident.Status.CLOSED:
                raise AFValidationError(
                    "Employees can only transition OPEN incidents to CLOSED."
                )
        else:
            # HR Manager / Org Admin
            if current_status == Incident.Status.OPEN:
                if new_status not in (Incident.Status.IN_PROGRESS, Incident.Status.CLOSED):
                    raise AFValidationError(
                        "OPEN incidents can only transition to IN_PROGRESS or CLOSED."
                    )
            elif current_status == Incident.Status.IN_PROGRESS:
                if new_status not in (Incident.Status.RESOLVED, Incident.Status.CLOSED):
                    raise AFValidationError(
                        "IN_PROGRESS incidents can only transition to RESOLVED or CLOSED."
                    )

        incident.status = new_status
        if new_status == Incident.Status.RESOLVED:
            incident.resolved_at = timezone.now()
        elif new_status == Incident.Status.CLOSED:
            incident.closed_at = timezone.now()

        incident.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])

    def perform_create(self, serializer):
        user = self.request.user
        employee = getattr(user, "employee_profile", None)
        
        asset = serializer.validated_data.get("asset")
        incident_category = serializer.validated_data.get("category")
        
        if asset and incident_category:
            from apps.assets.models import AssetCategory
            from apps.incidents.models import Incident
            asset_type = asset.category.category_type
            if asset_type == AssetCategory.CategoryType.SOFTWARE:
                if incident_category in (Incident.Category.HARDWARE, Incident.Category.PHYSICAL_DAMAGE):
                    raise AFValidationError(f"Cannot report a {incident_category.replace('_', ' ').title()} incident for a Software asset.")

        if getattr(user, "role", "EMPLOYEE") == "EMPLOYEE":
            requested_reported_by = serializer.validated_data.get("reported_by")
            if requested_reported_by and requested_reported_by != employee:
                raise AFValidationError("You can only report incidents for yourself and your own assigned assets.")

            reported_by = employee
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
            incident_number=generate_reference_number(settings.REF_PREFIX_INCIDENT),
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

    @action(detail=True, methods=["post"], url_path="status",
            permission_classes=[IsAuthenticated])
    def change_status(self, request, pk=None):
        incident = self.get_object()
        user = request.user

        serializer = IncidentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        role = getattr(user, "role", "EMPLOYEE")
        employee_profile = getattr(user, "employee_profile", None)

        if incident.status == new_status:
            return Response(IncidentSerializer(incident).data)

        self._apply_incident_status_transition(
            incident, new_status, role, employee_profile
        )

        NotificationService.notify_incident_updated(incident)

        return Response(IncidentSerializer(incident).data)

    @action(detail=False, methods=["post"], url_path="bulk-status",
            permission_classes=[IsAuthenticated])
    def bulk_status_update(self, request):
        serializer = BulkIncidentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        incident_ids = serializer.validated_data["incident_ids"]
        new_status = serializer.validated_data["status"]
        user = request.user
        role = getattr(user, "role", "EMPLOYEE")
        employee_profile = getattr(user, "employee_profile", None)

        updated_count = 0
        errors = []

        incidents = Incident.objects.filter(id__in=incident_ids)
        incident_map = {str(inc.id): inc for inc in incidents}

        for inc_id in incident_ids:
            inc_id_str = str(inc_id)
            incident = incident_map.get(inc_id_str)
            if not incident:
                errors.append({"id": inc_id_str, "error": "Not found."})
                continue

            # Same-status is a silent no-op (counts as updated)
            if incident.status == new_status:
                updated_count += 1
                continue

            try:
                self._apply_incident_status_transition(
                    incident, new_status, role, employee_profile
                )
                NotificationService.notify_incident_updated(incident)
                updated_count += 1
            except AFValidationError as e:
                error_msg = e.detail.get("message", str(e)) if isinstance(e.detail, dict) else str(e.detail)
                errors.append({"id": inc_id_str, "error": error_msg})

        return Response({
            "message": f"Successfully updated {updated_count} incidents.",
            "updated_count": updated_count,
            "errors": errors
        })


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
