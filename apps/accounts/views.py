from django.db import connection
from rest_framework import status, serializers as drf_serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, inline_serializer

from apps.accounts.models import User
from apps.accounts.serializers import (
    LoginSerializer,
    UserSerializer,
    UserCreateSerializer,
    ChangePasswordSerializer,
)
from apps.base.permissions import IsSuperAdmin, IsOrganizationAdmin, IsOrgAdminOrHR


# ── Response-only serializers for Swagger docs ──────────────────────────

class TokenResponseSerializer(drf_serializers.Serializer):
    access = drf_serializers.CharField()
    refresh = drf_serializers.CharField()
    user = UserSerializer()


class TokenPairSerializer(drf_serializers.Serializer):
    access = drf_serializers.CharField()
    refresh = drf_serializers.CharField()


class RefreshRequestSerializer(drf_serializers.Serializer):
    refresh = drf_serializers.CharField(help_text="Valid refresh token")


class MessageSerializer(drf_serializers.Serializer):
    message = drf_serializers.CharField()


# ── Views ────────────────────────────────────────────────────────────────

@extend_schema(tags=["Platform Auth"])
class PlatformLoginView(APIView):
    """Super Admin login — public schema only."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Platform Super Admin Login",
        request=LoginSerializer,
        responses={200: TokenResponseSerializer, 403: MessageSerializer},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        if not user.is_superuser:
            return Response(
                {"message": "Access denied. Platform login is for super admins only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        refresh["scope"] = "platform"
        refresh["role"] = user.role

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        })


@extend_schema(tags=["Tenant Auth"])
class TenantLoginView(APIView):
    """Tenant user login — tenant schema only."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Tenant User Login",
        request=LoginSerializer,
        responses={200: TokenResponseSerializer},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        tenant = connection.tenant
        refresh = RefreshToken.for_user(user)
        refresh["scope"] = "tenant"
        refresh["role"] = user.role
        refresh["tenant_slug"] = getattr(tenant, "slug", "")
        refresh["tenant_schema"] = getattr(tenant, "schema_name", "")

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        })


@extend_schema(tags=["Platform Auth"])
class TokenRefreshView(APIView):
    """Refresh an access token using a valid refresh token."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Refresh Access Token",
        request=RefreshRequestSerializer,
        responses={200: TokenPairSerializer, 400: MessageSerializer, 401: MessageSerializer},
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"message": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            return Response({
                "access": str(token.access_token),
                "refresh": str(token),
            })
        except Exception:
            return Response(
                {"message": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


@extend_schema(tags=["Tenant Auth"])
class ProfileView(APIView):
    """Get or update current user profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get My Profile",
        responses={200: UserSerializer},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        summary="Update My Profile",
        request=UserSerializer,
        responses={200: UserSerializer},
    )
    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


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


@extend_schema(tags=["Tenant Auth"])
class TenantUserViewSet(APIView):
    """
    Organization Admin creates tenant users.
    GET  /api/v1/auth/users/         -> list all users in this tenant
    POST /api/v1/auth/users/         -> create a new tenant user
    """

    permission_classes = [IsAuthenticated, IsOrgAdminOrHR]

    @extend_schema(
        summary="List Tenant Users",
        responses={200: UserSerializer(many=True)},
    )
    def get(self, request):
        users = User.objects.filter(is_active=True).order_by("-created_at")
        return Response(UserSerializer(users, many=True).data)

    @extend_schema(
        summary="Create Tenant User",
        request=UserCreateSerializer,
        responses={201: UserSerializer, 403: MessageSerializer},
    )
    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role = serializer.validated_data.get("role", User.Role.EMPLOYEE)
        if role == User.Role.SUPER_ADMIN:
            return Response(
                {"message": "Cannot create super admin from tenant context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
