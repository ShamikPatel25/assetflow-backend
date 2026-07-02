from rest_framework import serializers

from apps.tenants.models import Organization, Domain
from apps.accounts.utils import send_invitation_email
from apps.employees.models import TenantUser
from apps.employees.models import Employee
from apps.employees.utils import generate_employee_code
from django.db import connection
from django_tenants.utils import tenant_context
import re


class OrganizationCreateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    subdomain = serializers.CharField(
        write_only=True, 
        required=True, 
        help_text="Subdomain for the tenant (e.g., 'abc'). Required on creation."
    )
    org_admin_email = serializers.EmailField(
        write_only=True,
        required=True,
        help_text="Email address for the first Organization Admin. Required on creation."
    )

    class Meta:
        model = Organization
        fields = [
            "id", "name", "subdomain", "org_admin_email",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]

    def validate_subdomain(self, value):
        value = value.lower().strip()
        if not re.match(r'^[a-z0-9]+$', value):
            raise serializers.ValidationError("Subdomain can only contain lowercase letters and numbers. Special characters are not allowed.")

        domain_name = f"{value}.localhost"
        if Domain.objects.filter(domain=domain_name).exists():
            raise serializers.ValidationError("This subdomain is already in use.")

        # Check if the schema already exists in the database to prevent dangling schema errors
        schema_name = f"tenant_{value}"
        with connection.cursor() as cursor:
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", [schema_name])
            if cursor.fetchone():
                raise serializers.ValidationError("This subdomain is already in use (schema exists).")

        return value

    def validate_org_admin_email(self, value):
        if " " in value:
            raise serializers.ValidationError("Email cannot contain spaces.")
        if any(char.isupper() for char in value):
            raise serializers.ValidationError("Email must be in lowercase.")
        return value

    def create(self, validated_data):

        subdomain = validated_data.pop("subdomain")
        org_admin_email = validated_data.pop("org_admin_email")
        
        # Schema name is derived from subdomain directly
        validated_data["schema_name"] = f"tenant_{subdomain.replace('-', '_')}"
        
        # Create organization (schema gets created here automatically)
        org = super().create(validated_data)
        
        # Create the primary domain
        domain_name = f"{subdomain}.localhost"
        Domain.objects.create(
            domain=domain_name,
            tenant=org,
            is_primary=True,
        )


        # Switch to the new tenant schema and create the first Org Admin user
        with tenant_context(org):
            
            admin_user = TenantUser(
                email=org_admin_email,
                role=TenantUser.Role.ORGANIZATION_ADMIN,
                is_active=False  # Must be activated via invitation link
            )
            admin_user.set_unusable_password()
            admin_user.save()

            code = generate_employee_code("Pending", "")
            Employee.objects.create(
                user=admin_user,
                first_name="Pending",
                last_name="",
                employee_code=code,
            )

            send_invitation_email(admin_user, org.name, domain_name)

        return org


class OrganizationSuperAdminUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer used by the Super Admin to update the organization.
    They can update everything, including the subdomain.
    """
    id = serializers.UUIDField(read_only=True)
    subdomain = serializers.CharField(
        required=False,
        help_text="Subdomain for the tenant. Changing this renames the schema."
    )
    org_admin_email = serializers.EmailField(
        required=False,
        write_only=True,
        help_text="Change the email of the primary Organization Admin."
    )

    class Meta:
        model = Organization
        fields = [
            "id", "name", "subdomain", "org_admin_email",
            "contact_email", "contact_phone", "address",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Fetch the subdomain to display
        domain_obj = Domain.objects.filter(tenant=instance, is_primary=True).first()
        if domain_obj:
            ret['subdomain'] = domain_obj.domain.replace('.localhost', '')
        return ret

    def validate_subdomain(self, value):
        value = value.lower().strip()
        if not re.match(r'^[a-z0-9]+$', value):
            raise serializers.ValidationError("Subdomain can only contain lowercase letters and numbers. Special characters are not allowed.")

        domain_name = f"{value}.localhost"
        if Domain.objects.filter(domain=domain_name).exclude(tenant=self.instance).exists():
            raise serializers.ValidationError("This subdomain is already in use by another organization.")

        schema_name = f"tenant_{value}"
        if not self.instance or self.instance.schema_name != schema_name:
            with connection.cursor() as cursor:
                cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", [schema_name])
                if cursor.fetchone():
                    raise serializers.ValidationError("This subdomain is already in use (schema exists).")

        return value

    def validate_org_admin_email(self, value):
        if " " in value:
            raise serializers.ValidationError("Email cannot contain spaces.")
        if any(char.isupper() for char in value):
            raise serializers.ValidationError("Email must be in lowercase.")
        return value

    def validate_contact_phone(self, value):
        if not value:
            return value
        if not value.isdigit():
            raise serializers.ValidationError("Only numbers are allowed.")
        if not (10 <= len(value) <= 15):
            raise serializers.ValidationError("10-15 digits only allowed.")
        return value

    def update(self, instance, validated_data):

        new_subdomain = validated_data.pop("subdomain", None)
        new_admin_email = validated_data.pop("org_admin_email", None)

        old_schema_name = instance.schema_name

        # Update base fields
        instance = super().update(instance, validated_data)

        # Handle Subdomain / Schema change
        if new_subdomain:
            new_schema_name = f"tenant_{new_subdomain.replace('-', '_')}"
            domain_name = f"{new_subdomain}.localhost"

            # Check if it actually changed
            if new_schema_name != old_schema_name:
                # 1. Update Domain record
                domain_obj = Domain.objects.filter(tenant=instance, is_primary=True).first()
                if domain_obj:
                    domain_obj.domain = domain_name
                    domain_obj.save()
                else:
                    Domain.objects.create(domain=domain_name, tenant=instance, is_primary=True)

                # 2. Rename PostgreSQL Schema
                with connection.cursor() as cursor:
                    cursor.execute(f'ALTER SCHEMA "{old_schema_name}" RENAME TO "{new_schema_name}"')
                
                # 3. Update the Organization record's schema_name
                instance.schema_name = new_schema_name
                instance.save(update_fields=['schema_name'])

        # Handle Org Admin email change
        if new_admin_email:
            with tenant_context(instance):
                # Find an existing org admin to update
                admin_user = TenantUser.objects.filter(role=TenantUser.Role.ORGANIZATION_ADMIN).first()
                if admin_user:
                    admin_user.email = new_admin_email
                    admin_user.save(update_fields=['email'])

        return instance


class OrganizationTenantUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer used by the Organization Admin to update their own organization.
    They cannot update the name, subdomain, or org_admin_email.
    """
    id = serializers.UUIDField(read_only=True)
    subdomain = serializers.CharField(read_only=True)
    org_admin_email = serializers.EmailField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id", "name", "subdomain", "org_admin_email",
            "contact_email", "contact_phone", "address",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "name", "subdomain", "org_admin_email", "created_at", "updated_at"]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Fetch the subdomain to display
        domain_obj = Domain.objects.filter(tenant=instance, is_primary=True).first()
        if domain_obj:
            ret['subdomain'] = domain_obj.domain.replace('.localhost', '')
        return ret

    def validate_contact_phone(self, value):
        if not value:
            return value
        if not value.isdigit():
            raise serializers.ValidationError("Only numbers are allowed.")
        if not (10 <= len(value) <= 15):
            raise serializers.ValidationError("10-15 digits only allowed.")
        return value


class DomainSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Domain
        fields = ["id", "domain", "tenant", "is_primary", "verified_at", "created_at", "updated_at"]
        read_only_fields = ["id", "verified_at", "created_at", "updated_at"]
