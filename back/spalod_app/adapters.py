from allauth.account.adapter import DefaultAccountAdapter
from allauth.account import app_settings
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import resolve, Resolver404

User = get_user_model()

class CustomAccountAdapter(DefaultAccountAdapter):
    """Only enforce unique-email on registration endpoints."""
    def _is_registration_request(self):
        request = getattr(self, "request", None)
        if not request:
            return False
        try:
            match = resolve(request.path_info)
            return match.url_name in {"rest_register", "account_signup", "socialaccount_signup"}
        except Resolver404:
            return False
        
    def clean_email(self, email):
        # Normalize email
        email = (email or "").strip().lower()
        if app_settings.UNIQUE_EMAIL and self._is_registration_request():
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError("A user is already registered with this e-mail address.")

        return email