from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data["email"].lower().strip()
        password = data["password"]
        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")
        data["user"] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "phone",
            "role", "is_active", "last_login", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "last_login", "created_at", "updated_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "phone",
            "role"
        ]
        read_only_fields = ["id"]

    def validate_email(self, value):
        return value.lower().strip()

    def create(self, validated_data):
        from apps.accounts.utils import send_invitation_email
        from django.db import connection

        user = User(**validated_data)
        user.is_active = False  # Account must be activated via link
        user.set_unusable_password()
        user.save()
        
        # Get current tenant details
        tenant = connection.tenant
        domain_obj = tenant.domains.filter(is_primary=True).first()
        domain_name = domain_obj.domain if domain_obj else "localhost"

        send_invitation_email(user, tenant.name, domain_name)
        
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
