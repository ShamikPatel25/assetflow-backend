from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema

from apps.accounts.serializers_invitation import (
    InvitationValidateSerializer,
    InvitationSetupSerializer,
    InvitationResendSerializer,
)


class InvitationValidateView(APIView):
    """
    Validates an invitation token and returns the associated email.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=InvitationValidateSerializer, responses={200: {"type": "object", "properties": {"email": {"type": "string"}}}})
    def post(self, request, *args, **kwargs):
        serializer = InvitationValidateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.context["user"]
        return Response({"email": user.email}, status=status.HTTP_200_OK)


class InvitationSetupView(APIView):
    """
    Completes account setup using an invitation token.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=InvitationSetupSerializer, responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}})
    def post(self, request, *args, **kwargs):
        serializer = InvitationSetupSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Account setup successfully."}, status=status.HTTP_200_OK)


class InvitationResendView(APIView):
    """
    Resends an invitation email for an inactive user.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=InvitationResendSerializer, responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}})
    def post(self, request, *args, **kwargs):
        serializer = InvitationResendSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Invitation resent successfully."}, status=status.HTTP_200_OK)
