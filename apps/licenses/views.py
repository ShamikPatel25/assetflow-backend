from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema
from django.db import transaction
from django.utils import timezone

from apps.base.permissions import IsOrgAdminOrHR, IsOrgAdminOrHROrReadOnly
from apps.base.views import CRUDViewSet, ReadOnlyViewSet
from apps.licenses.models import SoftwareLicense, LicenseAssignment
from apps.licenses.serializers import (
    SoftwareLicenseSerializer,
    LicenseAssignmentSerializer,
    AssignLicenseSerializer,
    RevokeLicenseSerializer,
    BulkAssignLicenseItemSerializer,
)
from apps.licenses.services import LicenseService


@extend_schema_view(
    list=extend_schema(tags=["Licenses"]),
    create=extend_schema(tags=["Licenses"]),
    retrieve=extend_schema(tags=["Licenses"]),
    update=extend_schema(tags=["Licenses"]),
    partial_update=extend_schema(tags=["Licenses"]),
    destroy=extend_schema(tags=["Licenses"]),
    assign_license=extend_schema(
        tags=["Licenses"],
        summary="Assign License to Employee",
        request=AssignLicenseSerializer,
        responses={201: LicenseAssignmentSerializer},
    ),
    revoke_license=extend_schema(
        tags=["Licenses"],
        summary="Revoke License Assignment",
        request=RevokeLicenseSerializer,
        responses={200: LicenseAssignmentSerializer},
    ),
    bulk_assign=extend_schema(
        tags=["Licenses"],
        summary="Bulk Assign License to Employees",
        request=BulkAssignLicenseItemSerializer(many=True),
        responses={201: LicenseAssignmentSerializer(many=True)},
    ),
)
class SoftwareLicenseViewSet(CRUDViewSet):
    """
    CRUD for software licenses with assign/revoke actions.
    POST /api/v1/licenses/{id}/assign/      -> assign a seat
    POST /api/v1/licenses/{id}/bulk-assign/ -> bulk assign seats
    POST /api/v1/licenses/{id}/revoke/      -> revoke an assignment
    """

    queryset = SoftwareLicense.objects.all()
    serializer_class = SoftwareLicenseSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHROrReadOnly]
    search_fields = ["name", "vendor"]
    ordering_fields = ["name", "expiry_date", "created_at"]
    filterset_fields = ["status", "license_type"]

    def perform_destroy(self, instance):
        """
        Soft-delete the license AND bulk-revoke all its active assignments
        in one atomic transaction.

        Rationale: if the parent license is deleted, leaving assignments
        in ACTIVE state is inconsistent — those employees would appear to
        hold seats on a license that no longer exists.
        """
        with transaction.atomic():
            now = timezone.now()

            # Revoke every active assignment on this license
            active_assignments = LicenseAssignment.objects.filter(
                license=instance,
                status=LicenseAssignment.Status.ACTIVE,
                is_deleted=False,
            )
            active_assignments.update(
                status=LicenseAssignment.Status.REVOKED,
                revoked_at=now,
                updated_at=now,
                updated_by=self.request.user,
            )

            # Soft-delete the license itself (standard base behaviour)
            instance.is_deleted = True
            instance.updated_by = self.request.user
            instance.save(update_fields=["is_deleted", "updated_by", "updated_at"])

    @action(detail=True, methods=["post"], url_path="assign",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def assign_license(self, request, pk=None):
        license_obj = self.get_object()
        serializer = AssignLicenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = serializer.validated_data["employee"]
        assigned_by = getattr(request.user, "employee_profile", None)

        assignment = LicenseService.assign(
            license_obj=license_obj,
            employee=employee,
            assigned_by=assigned_by,
            created_by=request.user,
        )

        return Response(
            LicenseAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="revoke",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def revoke_license(self, request, pk=None):
        serializer = RevokeLicenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            assignment = LicenseAssignment.objects.get(
                pk=serializer.validated_data["assignment"]
            )
        except LicenseAssignment.DoesNotExist:
            raise NotFound({"message": "License assignment not found."})

        assignment = LicenseService.revoke(assignment, updated_by=request.user)
        return Response(LicenseAssignmentSerializer(assignment).data)

    @action(detail=True, methods=["post"], url_path="bulk-assign",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def bulk_assign(self, request, pk=None):
        license_obj = self.get_object()
        serializer = BulkAssignLicenseItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        assignments_data = serializer.validated_data
        assigned_by = getattr(request.user, "employee_profile", None)

        assignments = LicenseService.bulk_assign(
            license_obj=license_obj,
            assignments_data=assignments_data,
            assigned_by=assigned_by,
            created_by=request.user,
        )

        return Response(
            LicenseAssignmentSerializer(assignments, many=True).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    list=extend_schema(tags=["Licenses"]),
    retrieve=extend_schema(tags=["Licenses"]),
)
class LicenseAssignmentViewSet(ReadOnlyViewSet):
    """List and manage license assignments."""

    queryset = LicenseAssignment.objects.select_related("license", "employee")
    serializer_class = LicenseAssignmentSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHROrReadOnly]
    search_fields = ["license__name", "employee__first_name"]
    filterset_fields = ["status", "license", "employee"]
