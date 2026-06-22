from django.db import connection
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken


class TenantJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that correctly resolves the user
    based on the current tenant schema.
    """

    def get_user(self, validated_token):
        """
        Attempts to find and return a user using the given validated token.
        """
        from rest_framework_simplejwt.settings import api_settings
        
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken(_("Token contained no recognizable user identification"))

        if connection.schema_name == "public":
            from apps.accounts.models import User
            UserModel = User
        else:
            from apps.employees.models import TenantUser
            UserModel = TenantUser

        try:
            user = UserModel.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except UserModel.DoesNotExist:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        if not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

        return user


from drf_spectacular.extensions import OpenApiAuthenticationExtension

class TenantJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'apps.base.authentication.TenantJWTAuthentication'
    name = 'Bearer'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
