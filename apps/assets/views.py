from django.http import Http404, HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.exceptions import NotFound
from drf_spectacular.utils import extend_schema_view, extend_schema
from drf_spectacular.types import OpenApiTypes

from apps.base.permissions import IsOrgAdminOrHROrReadOnly
from apps.base.views import CRUDViewSet
from apps.assets.models import AssetCategory, Asset
from apps.assets.serializers import AssetCategorySerializer, AssetSerializer
from apps.assets.services.excel_service import export_assets_to_excel, import_assets_from_excel


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
        except (Http404, NotFound):
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

    @extend_schema(
        tags=["Assets"],
        summary="Export assets to Excel",
        description="Exports the filtered list of assets to an Excel (.xlsx) file."
    )
    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        excel_data = export_assets_to_excel(queryset)
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="assets_export.xlsx"'
        return response

    @extend_schema(
        tags=["Assets"],
        summary="Import assets from Excel",
        description="Upload an Excel file to bulk create new assets.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"}
                },
                "required": ["file"]
            }
        },
        responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def import_excel(self, request):
        if 'file' not in request.FILES:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        
        if not file_obj.name.lower().endswith('.xlsx'):
            return Response({"error": "Invalid file format. Please upload a valid .xlsx Excel file."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            result = import_assets_from_excel(file_obj, user=request.user)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            error_msg = str(e)
            if "valid workbook part" in error_msg.lower() or "zipfile" in error_msg.lower():
                return Response({"error": "The uploaded file is corrupted or not a valid Excel file. Please upload a valid .xlsx file."}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"error": f"Failed to process file: {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
