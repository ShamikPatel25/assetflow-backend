from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.permissions import IsOrgAdminOrHROrReadOnly
from apps.base.views import CRUDViewSet
from apps.assets.models import AssetCategory, Asset
from apps.assets.serializers import AssetCategorySerializer, AssetSerializer


@extend_schema_view(
    list=extend_schema(tags=["Assets"]),
    create=extend_schema(tags=["Assets"]),
    retrieve=extend_schema(tags=["Assets"]),
    update=extend_schema(tags=["Assets"]),
    partial_update=extend_schema(tags=["Assets"]),
    destroy=extend_schema(tags=["Assets"]),
)
class AssetCategoryViewSet(CRUDViewSet):
    """CRUD for asset categories. Org Admin and HR Manager manage, others read."""

    queryset = AssetCategory.objects.select_related("parent")
    serializer_class = AssetCategorySerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHROrReadOnly]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "created_at"]
    filterset_fields = ["category_type", "is_active", "parent"]

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return super().destroy(request, *args, **kwargs)

        if instance.children.filter(is_deleted=False).exists():
            return Response(
                {"message": "Cannot delete category because it has active child categories. Please delete them first."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(tags=["Assets"]),
    create=extend_schema(tags=["Assets"]),
    retrieve=extend_schema(tags=["Assets"]),
    update=extend_schema(tags=["Assets"]),
    partial_update=extend_schema(tags=["Assets"]),
    destroy=extend_schema(tags=["Assets"]),
)
class AssetViewSet(CRUDViewSet):
    """CRUD for assets. Org Admin and HR Manager manage, others read."""

    queryset = Asset.objects.select_related("category", "current_owner")
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHROrReadOnly]
    search_fields = ["asset_code", "name", "brand", "model", "serial_number"]
    ordering_fields = ["asset_code", "name", "purchase_date", "created_at", "status"]
    filterset_fields = ["status", "condition", "category", "is_active"]
