from rest_framework import views
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.ai.serializers import RiskAssessmentRequestSerializer, RiskAssessmentResponseSerializer
from apps.ai.services import RiskAssessmentService
from apps.base.permissions import IsOrgAdminOrHR


@extend_schema(tags=["AI Services"])
class AIRiskAssessmentView(views.APIView):
    """
    AI-powered Risk Assessment Engine.
    Pass an action (APPROVE_REQUEST or ALLOCATE_ASSET) and the relevant IDs,
    and the AI will analyze the employee's history to output a risk score.
    """

    permission_classes = [IsAuthenticated, IsOrgAdminOrHR]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ai_requests'

    @extend_schema(
        request=RiskAssessmentRequestSerializer,
        responses={200: RiskAssessmentResponseSerializer}
    )
    def post(self, request, *args, **kwargs):
        serializer = RiskAssessmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]

        if action == "APPROVE_REQUEST":
            request_id = serializer.validated_data["request_id"]
            ai_response = RiskAssessmentService.assess_request(request_id)
            return Response(ai_response)

        elif action == "ALLOCATE_ASSET":
            employee_id = serializer.validated_data["employee_id"]
            asset_id = serializer.validated_data["asset_id"]
            ai_response = RiskAssessmentService.assess_allocation(employee_id, asset_id)
            return Response(ai_response)
