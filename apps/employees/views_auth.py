from django.db import connection
from rest_framework import status, serializers as drf_serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema

from apps.employees.models import Employee
from apps.employees.serializers_auth import (
    TenantLoginSerializer,
    TenantUserSerializer,
    EmployeeProfileSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
)

class TokenResponseSerializer(drf_serializers.Serializer):
    access = drf_serializers.CharField()
    refresh = drf_serializers.CharField()
    user = TenantUserSerializer()
    profile = EmployeeProfileSerializer()

    class Meta:
        ref_name = "EmployeesTokenResponse"

class MessageSerializer(drf_serializers.Serializer):
    message = drf_serializers.CharField()

    class Meta:
        ref_name = "EmployeesMessage"


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


class LogoutRequestSerializer(drf_serializers.Serializer):
    refresh = drf_serializers.CharField(help_text="The refresh token to invalidate.")

    class Meta:
        ref_name = "EmployeesLogoutRequest"


@extend_schema(tags=["Tenant Auth"])
class LogoutView(APIView):
    """
    Blacklist the refresh token to invalidate the session.
    After calling this endpoint the provided refresh token (and its rotated
    descendants) can no longer be used to obtain new access tokens.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout / Blacklist Refresh Token",
        request=LogoutRequestSerializer,
        responses={200: MessageSerializer, 400: MessageSerializer},
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"message": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from django.core.cache import cache
            token = RefreshToken(refresh_token)
            
            # Use Django cache for token blacklisting (faster & avoids TenantUser model conflict)
            jti = token["jti"]
            if cache.get(f"blacklisted_{jti}"):
                return Response(
                    {"message": "Token is invalid or has already been blacklisted."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
                
            timeout = token.lifetime.total_seconds()
            cache.set(f"blacklisted_{jti}", True, timeout=timeout)

        except TokenError:
            return Response(
                {"message": "Token is invalid or has already been blacklisted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"message": "Logged out successfully."})


@extend_schema(tags=["Tenant Auth"])
class ForgotPasswordView(APIView):
    """Request a password reset link."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Forgot Password",
        request=ForgotPasswordSerializer,
        responses={200: MessageSerializer},
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()
        
        from apps.employees.models import TenantUser
        user = TenantUser.objects.filter(email=email).first()
        
        if user and user.is_active:
            from apps.accounts.utils import send_password_reset_email
            tenant = connection.tenant
            domain_obj = tenant.domains.filter(is_primary=True).first()
            domain_name = domain_obj.domain if domain_obj else "localhost"
            send_password_reset_email(user, tenant.name, domain_name)

        # Always return the same message to prevent email enumeration
        return Response(
            {"message": "If an account with that email exists, a password reset link has been sent. It will expire in 1 hour."},
            status=status.HTTP_200_OK
        )


@extend_schema(tags=["Tenant Auth"])
class ResetPasswordView(APIView):
    """Reset password using the token sent via email."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Reset Password",
        request=ResetPasswordSerializer,
        responses={200: MessageSerializer, 400: MessageSerializer},
    )
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        import jwt
        from django.conf import settings
        from apps.employees.models import TenantUser

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != "password_reset":
                raise jwt.InvalidTokenError("Invalid token type.")
            
            user = TenantUser.objects.get(id=payload.get("user_id"))
            
            # Verify the single-use hash
            current_hash = user.password[-20:] if user.password else ""
            if payload.get("hash") != current_hash:
                raise jwt.InvalidTokenError("This token has already been used.")
                
            user.set_password(new_password)
            user.save(update_fields=["password", "updated_at"])
            
            return Response({"message": "Password has been reset successfully."}, status=status.HTTP_200_OK)
            
        except jwt.ExpiredSignatureError:
            return Response({"message": "Token has expired."}, status=status.HTTP_400_BAD_REQUEST)
        except (jwt.InvalidTokenError, TenantUser.DoesNotExist):
            return Response({"message": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
