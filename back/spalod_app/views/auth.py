from django.conf import settings
from django.views.generic.base import RedirectView


class PasswordResetConfirmRedirect(RedirectView):
    permanent = False
    query_string = True  
    def get_redirect_url(self, uidb64=None, token=None, **kwargs):
        base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:8080").rstrip("/")
        return f"{base}/reset-password/{uidb64}/{token}"

