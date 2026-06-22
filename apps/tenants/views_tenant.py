from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.base.permissions import IsOrgAdminOrReadOnly
from apps.tenants.serializers import OrganizationTenantUpdateSerializer


@extend_schema(tags=["Organization Settings"])
class TenantOrganizationSettingsView(generics.RetrieveUpdateAPIView):
    """
    Org Admin manages their own organization's settings.
    GET    /api/v1/organization/settings/
    PUT    /api/v1/organization/settings/
    PATCH  /api/v1/organization/settings/
    """
    serializer_class = OrganizationTenantUpdateSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrReadOnly]

    def get_object(self):
        # The tenant is automatically attached to the request by TenantRoutingMiddleware
        return self.request.tenant
