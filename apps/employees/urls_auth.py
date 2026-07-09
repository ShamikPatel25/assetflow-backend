from django.urls import path
from apps.employees.views_auth import (
    TenantLoginView,
    LogoutView,
    ProfileView,
    ChangePasswordView,
)

from apps.employees.views_invitation import (
    InvitationValidateView,
    InvitationSetupView,
    InvitationResendView,
)

urlpatterns = [
    path("login/", TenantLoginView.as_view(), name="tenant-login"),
    path("logout/", LogoutView.as_view(), name="tenant-logout"),
    path("profile/", ProfileView.as_view(), name="tenant-profile"),
    path("change-password/", ChangePasswordView.as_view(), name="tenant-change-password"),

    # Invitation endpoints
    path("invitation/validate/", InvitationValidateView.as_view(), name="invitation-validate"),
    path("invitation/setup/", InvitationSetupView.as_view(), name="invitation-setup"),
    path("invitation/resend/", InvitationResendView.as_view(), name="invitation-resend"),
]
