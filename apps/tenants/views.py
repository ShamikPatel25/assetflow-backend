import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.permissions import IsSuperAdmin
from apps.tenants.models import Organization, Domain
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers
from apps.tenants.serializers import (
    OrganizationCreateSerializer, 
    OrganizationSuperAdminUpdateSerializer, 
    DomainSerializer
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(tags=["Organizations"]),
    create=extend_schema(tags=["Organizations"]),
    retrieve=extend_schema(tags=["Organizations"]),
    update=extend_schema(tags=["Organizations"]),
    partial_update=extend_schema(tags=["Organizations"]),
    destroy=extend_schema(tags=["Organizations"]),
    activate=extend_schema(tags=["Organizations"]),
    deactivate=extend_schema(tags=["Organizations"]),
)
class OrganizationViewSet(ModelViewSet):
    """
    Super Admin manages organizations.
    POST   /api/v1/platform/organizations/
    GET    /api/v1/platform/organizations/
    GET    /api/v1/platform/organizations/{id}/
    PUT    /api/v1/platform/organizations/{id}/
    DELETE /api/v1/platform/organizations/{id}/
    POST   /api/v1/platform/organizations/{id}/activate/
    POST   /api/v1/platform/organizations/{id}/deactivate/
    """

    http_method_names = ["get", "post", "put", "delete"]
    queryset = Organization.objects.all()
    def get_serializer_class(self):
        if self.action == 'create':
            return OrganizationCreateSerializer
        if self.action in ['activate', 'deactivate']:
            return serializers.Serializer
        return OrganizationSuperAdminUpdateSerializer

    permission_classes = [IsAuthenticated, IsSuperAdmin]
    ordering = ("-created_at",)

    def perform_destroy(self, instance):
        instance.delete(force_drop=True)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        model_name = instance._meta.verbose_name.title()
        self.perform_destroy(instance)
        return Response(
            {"message": f"{model_name} deleted successfully, along with its tenant schema."},
            status=status.HTTP_200_OK
        )


    @extend_schema(
        request=None,
        responses={200: inline_serializer(
            name='ActivateResponse',
            fields={
                'message': serializers.CharField(),
                'id': serializers.UUIDField(),
                'is_active': serializers.BooleanField(),
            }
        )}
    )
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        org = self.get_object()
        if org.is_active:
            return Response({
                "message": "Organization is already active",
                "id": org.id,
                "is_active": org.is_active
            }, status=status.HTTP_200_OK)

        org.is_active = True
        org.save(update_fields=["is_active", "updated_at"])
        return Response({
            "message": "Organization activated successfully",
            "id": org.id,
            "is_active": org.is_active
        }, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses={200: inline_serializer(
            name='DeactivateResponse',
            fields={
                'message': serializers.CharField(),
                'id': serializers.UUIDField(),
                'is_active': serializers.BooleanField(),
            }
        )}
    )
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        org = self.get_object()
        if not org.is_active:
            return Response({
                "message": "Organization is already inactive",
                "id": org.id,
                "is_active": org.is_active
            }, status=status.HTTP_200_OK)

        org.is_active = False
        org.save(update_fields=["is_active", "updated_at"])
        return Response({
            "message": "Organization deactivated successfully",
            "id": org.id,
            "is_active": org.is_active
        }, status=status.HTTP_200_OK)

