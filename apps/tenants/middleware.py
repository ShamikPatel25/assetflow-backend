import logging

from django.db import connection
from django.http import JsonResponse
from django_tenants.middleware import TenantMainMiddleware

logger = logging.getLogger(__name__)


class TenantRoutingMiddleware(TenantMainMiddleware):
    """
    Resolves the current tenant from the request Host header.

    - If the host matches the platform domain, uses the public schema.
    - Otherwise, looks up the Domain table to find the tenant and
      switches the DB connection to that tenant's schema.
    """

    def process_request(self, request):
        super().process_request(request)

        # After django-tenants resolves the tenant, check if it's active
        tenant = connection.tenant
        if tenant and hasattr(tenant, "is_active") and not tenant.is_active:
            return JsonResponse(
                {"message": "This organization has been deactivated."},
                status=403,
            )
