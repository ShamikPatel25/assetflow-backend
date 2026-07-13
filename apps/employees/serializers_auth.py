from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.base.validators import validate_phone_number
from apps.employees.models import TenantUser, Employee


class TenantLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data["email"].lower().strip()
        password = data["password"]
        
        # We need to explicitly tell authenticate which backend to use 
        # or rely on the custom backend doing its job
        user = authenticate(email=email, password=password)
        if not user or not isinstance(user, TenantUser):
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")
            
        data["user"] = user
        return data


class TenantUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantUser
        fields = [
            "id", "email", "role", "is_active", "last_login", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "last_login", "created_at", "updated_at"]


class EmployeeProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = Employee
        fields = [
            "id", "first_name", "last_name", "phone",
            "employee_code", "designation", "department", "manager",
            "joining_date", "exit_date",
        ]
        read_only_fields = [
            "id", "employee_code", "designation", "department",
            "manager", "joining_date", "exit_date"
        ]

    def validate_phone(self, value):
        return validate_phone_number(value)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data
