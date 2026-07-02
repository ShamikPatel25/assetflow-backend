from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """Only platform super admins (staff users on public schema)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsOrganizationAdmin(BasePermission):
    """Only tenant users with ORGANIZATION_ADMIN role."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "ORGANIZATION_ADMIN"
        )


class IsOrgAdminOrHR(BasePermission):
    """Organization Admin or HR Manager."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(request.user, "role", None)
        return role in ("ORGANIZATION_ADMIN", "HR_MANAGER")


class IsOrgAdminOrReadOnly(BasePermission):
    """Organization Admin has full access, others get read-only."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return getattr(request.user, "role", None) == "ORGANIZATION_ADMIN"


class IsOrgAdminOrHROrReadOnly(BasePermission):
    """Organization Admin or HR Manager have full access, others get read-only."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        role = getattr(request.user, "role", None)
        return role in ("ORGANIZATION_ADMIN", "HR_MANAGER")
