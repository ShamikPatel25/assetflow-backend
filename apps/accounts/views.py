from rest_framework import status, serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema

from apps.accounts.serializers import LoginSerializer, UserSerializer


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
