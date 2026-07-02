import jwt
from django.conf import settings
from rest_framework import serializers

from apps.employees.models import TenantUser
from apps.accounts.utils import send_invitation_email
from django.db import connection

class InvitationValidateSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

    def validate_token(self, value):
        try:
            payload = jwt.decode(value, settings.SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != "invitation":
                raise serializers.ValidationError("Invalid token type.")
            
            user_id = payload.get("user_id")
            if not user_id:
                raise serializers.ValidationError("Invalid token payload.")
                
            user = TenantUser.objects.filter(id=user_id).first()
            if not user:
                raise serializers.ValidationError("User not found.")
            if user.is_active:
                raise serializers.ValidationError("User is already active.")
                
            self.context["user"] = user
            return value
            
        except jwt.ExpiredSignatureError:
            raise serializers.ValidationError("Token has expired.")
        except jwt.InvalidTokenError:
            raise serializers.ValidationError("Invalid token.")


class InvitationSetupSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, min_length=8)
    confirm_password = serializers.CharField(required=True, write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"password": "Passwords do not match."})
            
        # Validate token and attach user to context
        token_validator = InvitationValidateSerializer(data={"token": attrs["token"]}, context=self.context)
        token_validator.is_valid(raise_exception=True)
        
        user = self.context["user"]
        if user.email.lower() != attrs["email"].lower():
            raise serializers.ValidationError({"email": "This email does not match the invitation token."})
            
        return attrs

    def save(self):
        user = self.context["user"]
        user.set_password(self.validated_data["password"])
        user.is_active = True
        user.save(update_fields=["password", "is_active", "updated_at"])
        
        return user


class InvitationResendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        user = TenantUser.objects.filter(email=value).first()
        if not user:
            raise serializers.ValidationError("No user found with this email.")
        if user.is_active:
            raise serializers.ValidationError("User is already active.")
        self.context["user"] = user
        return value

    def save(self):

        user = self.context["user"]
        tenant = connection.tenant

        # Get primary domain
        domain_obj = tenant.domains.filter(is_primary=True).first()
        domain_name = domain_obj.domain if domain_obj else "localhost"

        send_invitation_email(user, tenant.name, domain_name)
