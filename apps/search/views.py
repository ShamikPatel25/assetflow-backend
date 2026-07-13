from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.assets.models import Asset
from django.conf import settings
from apps.employees.models import Employee
from apps.incidents.models import Incident
from apps.requests.models import AssetRequest
from apps.licenses.models import SoftwareLicense
from apps.search.serializers import GlobalSearchResponseSerializer

class GlobalSearchView(APIView):
    """
    Search across Assets, Employees, Incidents, Requests, and Licenses.
    GET /api/v1/search/?q=term
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Search"],
        parameters=[
            OpenApiParameter(name="q", description="Search query string", required=False, type=str),
        ],
        responses={200: GlobalSearchResponseSerializer}
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"results": []})

        results = []
        limit = settings.GLOBAL_SEARCH_LIMIT

        # 1. Assets
        assets = Asset.objects.filter(
            is_deleted=False,
        ).filter(
            Q(name__icontains=query) |
            Q(asset_code__icontains=query) |
            Q(serial_number__icontains=query)
        )[:limit]
        
        for asset in assets:
            results.append({
                "id": asset.id,
                "type": "ASSET",
                "title": asset.name,
                "subtitle": f"{asset.asset_code} ({asset.status})",
                "url": f"/api/v1/assets/{asset.id}/"
            })

        # 2. Employees
        employees = Employee.objects.filter(
            is_deleted=False,
        ).filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(employee_code__icontains=query)
        )[:limit]

        for emp in employees:
            results.append({
                "id": emp.id,
                "type": "EMPLOYEE",
                "title": f"{emp.first_name} {emp.last_name}",
                "subtitle": f"{emp.user.email} ({emp.designation})",
                "url": f"/api/v1/employees/{emp.id}/"
            })

        # 3. Incidents
        incidents = Incident.objects.filter(
            is_deleted=False,
        ).filter(
            Q(incident_number__icontains=query) |
            Q(title__icontains=query)
        )[:limit]

        for inc in incidents:
            results.append({
                "id": inc.id,
                "type": "INCIDENT",
                "title": inc.title,
                "subtitle": f"{inc.incident_number} ({inc.status})",
                "url": f"/api/v1/incidents/{inc.id}/"
            })

        # 4. Requests
        requests = AssetRequest.objects.filter(
            is_deleted=False,
        ).filter(
            Q(request_number__icontains=query) |
            Q(reason__icontains=query)
        )[:limit]

        for req in requests:
            category_name = req.category.name if req.category else "General"
            results.append({
                "id": req.id,
                "type": "REQUEST",
                "title": f"Request: {category_name}",
                "subtitle": f"{req.request_number} ({req.status})",
                "url": f"/api/v1/requests/{req.id}/"
            })

        # 5. Licenses
        licenses = SoftwareLicense.objects.filter(
            is_deleted=False,
        ).filter(
            Q(name__icontains=query) |
            Q(license_key__icontains=query)
        )[:limit]

        for lic in licenses:
            results.append({
                "id": lic.id,
                "type": "LICENSE",
                "title": lic.name,
                "subtitle": f"Seats: {lic.total_seats}",
                "url": f"/api/v1/licenses/{lic.id}/"
            })

        return Response({"results": results})
