from django.urls import path
from apps.accounts.views import (
    TenantLoginView,
    TokenRefreshView,
    ProfileView,
    ChangePasswordView,
    TenantUserViewSet,
)

from apps.accounts.views_invitation import (
    InvitationValidateView,
    InvitationSetupView,
    InvitationResendView,
)

urlpatterns = [
    path("login/", TenantLoginView.as_view(), name="tenant-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="tenant-token-refresh"),
    path("profile/", ProfileView.as_view(), name="tenant-profile"),
    path("change-password/", ChangePasswordView.as_view(), name="tenant-change-password"),
    path("users/", TenantUserViewSet.as_view(), name="tenant-users"),
    
    # Invitation endpoints
    path("invitation/validate/", InvitationValidateView.as_view(), name="invitation-validate"),
    path("invitation/setup/", InvitationSetupView.as_view(), name="invitation-setup"),
    path("invitation/resend/", InvitationResendView.as_view(), name="invitation-resend"),
]
