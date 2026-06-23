from django.contrib.auth import authenticate
from rest_framework import serializers

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
        if not user:
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
    role = serializers.CharField(source='user.role', read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id", "first_name", "last_name", "phone", "role",
            "employee_code", "designation", "department", "manager",
            "joining_date", "exit_date",
        ]
        read_only_fields = [
            "id", "employee_code", "designation", "department", 
            "manager", "joining_date", "exit_date"
        ]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
