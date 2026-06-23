from django.contrib.auth.backends import ModelBackend
from apps.employees.models import TenantUser

class TenantAuthBackend(ModelBackend):
    """
    Custom authentication backend to authenticate tenant users against the 
    TenantUser model instead of the public User model.
    """
    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None:
            email = kwargs.get('username')
            
        try:
            user = TenantUser.objects.get(email=email)
        except TenantUser.DoesNotExist:
            return None
            
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
            
        return None

    def get_user(self, user_id):
        try:
            return TenantUser.objects.get(pk=user_id)
        except TenantUser.DoesNotExist:
            return None
