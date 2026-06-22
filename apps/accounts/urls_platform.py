from django.urls import path
from apps.accounts.views import PlatformLoginView, TokenRefreshView

urlpatterns = [
    path("login/", PlatformLoginView.as_view(), name="platform-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="platform-token-refresh"),
]
