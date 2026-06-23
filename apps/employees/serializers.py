from rest_framework import serializers

from apps.base.serializers import BaseModelSerializer
from apps.employees.models import Department, Employee


class DepartmentSerializer(BaseModelSerializer):
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = BaseModelSerializer.base_fields(
            "name", "code", "description",
            "manager", "manager_name",
        )

    def get_manager_name(self, obj) -> str | None:
        if obj.manager:
            return obj.manager.get_full_name()
        return None


class EmployeeSerializer(BaseModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    manager_name = serializers.SerializerMethodField()
    email = serializers.EmailField(required=False)

    class Meta:
        model = Employee
        fields = BaseModelSerializer.base_fields(
            "user", "email", "employee_code", "first_name", "last_name",
            "phone", "designation", "department", "department_name",
            "manager", "manager_name", "joining_date", "exit_date",
        )

    def get_manager_name(self, obj) -> str | None:
        if obj.manager:
            return obj.manager.get_full_name()
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.user:
            data["email"] = instance.user.email
        return data

    def validate(self, data):
        request = self.context.get("request")
        if request and self.instance:
            from apps.employees.models import TenantUser
            
            # Prevent HR Managers from editing Org Admins
            if request.user.role == TenantUser.Role.HR_MANAGER:
                if self.instance.user.role == TenantUser.Role.ORGANIZATION_ADMIN:
                    raise serializers.ValidationError("HR Managers cannot edit Organization Admin profiles.")

            # Validate email uniqueness if provided
            if "email" in data:
                new_email = data["email"]
                if TenantUser.objects.filter(email=new_email).exclude(id=self.instance.user.id).exists():
                    raise serializers.ValidationError({"email": "This email is already in use by another user."})
        
        return data

    def update(self, instance, validated_data):
        from django.db import transaction
        from apps.accounts.utils import send_invitation_email
        from django.db import connection
        
        new_email = validated_data.pop("email", None)
        
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            
            if new_email and instance.user.email != new_email:
                instance.user.email = new_email
                instance.user.save(update_fields=["email"])
                
                # If they haven't set up their account, resend the invite to the new email
                if not instance.user.is_active:
                    tenant = connection.tenant
                    domain_obj = tenant.domains.filter(is_primary=True).first()
                    domain_name = domain_obj.domain if domain_obj else "localhost"
                    send_invitation_email(instance.user, tenant.name, domain_name)
                        
        return instance

class EmployeeMinimalSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns and references."""

    class Meta:
        model = Employee
        fields = ["id", "employee_code", "first_name", "last_name"]


class EmployeeCreateSerializer(serializers.Serializer):
    from apps.employees.models import TenantUser
    
    first_name = serializers.CharField(required=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(required=True, max_length=20)
    designation = serializers.CharField(required=True, max_length=100, allow_blank=True)
    joining_date = serializers.DateField(required=True)
    
    department = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    manager = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    role = serializers.ChoiceField(choices=[
        (TenantUser.Role.ORGANIZATION_ADMIN, "Organization Admin"),
        (TenantUser.Role.HR_MANAGER, "HR Manager"),
        (TenantUser.Role.EMPLOYEE, "Employee"),
    ], required=True)

    def validate_email(self, value):
        from apps.employees.models import TenantUser
        if TenantUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use by another user.")
        return value

    def validate_role(self, value):
        from apps.employees.models import TenantUser
        request = self.context.get("request")
        if request and request.user.role == TenantUser.Role.HR_MANAGER:
            if value != TenantUser.Role.EMPLOYEE:
                raise serializers.ValidationError("HR Managers can only create standard Employees.")
        return value

    def validate_department(self, value):
        if not value:
            return None
        import uuid
        try:
            val = uuid.UUID(value)
        except ValueError:
            raise serializers.ValidationError("Must be a valid UUID.")
            
        from apps.employees.models import Department
        if not Department.objects.filter(id=val).exists():
            raise serializers.ValidationError("Invalid department ID.")
        return val

    def validate_manager(self, value):
        if not value:
            return None
        import uuid
        try:
            val = uuid.UUID(value)
        except ValueError:
            raise serializers.ValidationError("Must be a valid UUID.")
            
        from apps.employees.models import Employee
        if not Employee.objects.filter(id=val).exists():
            raise serializers.ValidationError("Invalid manager ID.")
        return val

    def create(self, validated_data):
        from django.db import transaction
        from apps.employees.models import TenantUser, Employee, Department
        from apps.employees.utils import generate_employee_code
        from apps.accounts.utils import send_invitation_email
        from django.db import connection
        
        email = validated_data.pop("email")
        role = validated_data.pop("role")
        
        department_id = validated_data.pop("department", None)
        manager_id = validated_data.pop("manager", None)

        with transaction.atomic():
            # Create TenantUser
            user = TenantUser(
                email=email,
                role=role,
                is_active=False
            )
            user.set_unusable_password()
            user.save()
            
            # Create Employee
            employee_code = generate_employee_code(validated_data["first_name"], validated_data["last_name"])
            
            department = Department.objects.get(id=department_id) if department_id else None
            manager = Employee.objects.get(id=manager_id) if manager_id else None
            
            employee = Employee.objects.create(
                user=user,
                employee_code=employee_code,
                department=department,
                manager=manager,
                **validated_data
            )
            
            # Send invitation email
            tenant = connection.tenant
            domain_obj = tenant.domains.filter(is_primary=True).first()
            domain_name = domain_obj.domain if domain_obj else "localhost"
            send_invitation_email(user, tenant.name, domain_name)
            
        return employee

    def to_representation(self, instance):
        # Use standard EmployeeSerializer for the output response
        from apps.employees.serializers import EmployeeSerializer
        return EmployeeSerializer(instance, context=self.context).data
