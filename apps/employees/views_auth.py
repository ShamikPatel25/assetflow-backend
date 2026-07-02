from django.db import connection
from rest_framework import status, serializers as drf_serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema

from apps.employees.models import Employee
from apps.employees.serializers_auth import (
    TenantLoginSerializer,
    TenantUserSerializer,
    EmployeeProfileSerializer,
    ChangePasswordSerializer,
)

class TokenResponseSerializer(drf_serializers.Serializer):
    access = drf_serializers.CharField()
    refresh = drf_serializers.CharField()
    user = TenantUserSerializer()
    profile = EmployeeProfileSerializer()

class MessageSerializer(drf_serializers.Serializer):
    message = drf_serializers.CharField()


@extend_schema(tags=["Tenant Auth"])
class TenantLoginView(APIView):
    """Tenant user login — tenant schema only."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Tenant User Login",
        request=TenantLoginSerializer,
        responses={200: TokenResponseSerializer},
    )
    def post(self, request):
        serializer = TenantLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        tenant = connection.tenant
        refresh = RefreshToken.for_user(user)
        refresh["scope"] = "tenant"
        refresh["role"] = user.role
        refresh["tenant_slug"] = getattr(tenant, "slug", "")
        refresh["tenant_schema"] = getattr(tenant, "schema_name", "")

        try:
            profile = user.employee_profile
            profile_data = EmployeeProfileSerializer(profile).data
        except Employee.DoesNotExist:
            profile_data = None

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": TenantUserSerializer(user).data,
            "profile": profile_data,
        })


class ProfileResponseSerializer(drf_serializers.Serializer):
    user = TenantUserSerializer()
    profile = EmployeeProfileSerializer()

@extend_schema(tags=["Tenant Auth"])
class ProfileView(APIView):
    """Get or update current user profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get My Profile",
        responses={200: ProfileResponseSerializer},
    )
    def get(self, request):
        try:
            profile = request.user.employee_profile
            return Response({
                "user": TenantUserSerializer(request.user).data,
                "profile": EmployeeProfileSerializer(profile).data
            })
        except Employee.DoesNotExist:
            return Response({"message": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(
        summary="Update My Profile",
        request=EmployeeProfileSerializer,
        responses={200: ProfileResponseSerializer},
    )
    def put(self, request):
        try:
            profile = request.user.employee_profile
        except Employee.DoesNotExist:
            return Response({"message": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = EmployeeProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            "user": TenantUserSerializer(request.user).data,
            "profile": serializer.data
        })


@extend_schema(tags=["Tenant Auth"])
class ChangePasswordView(APIView):
    """Change password for the currently logged-in user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change Password",
        request=ChangePasswordSerializer,
        responses={200: MessageSerializer},
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        return Response({"message": "Password changed successfully."})
