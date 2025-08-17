from allauth.account.adapter import DefaultAccountAdapter
from allauth.account import app_settings
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomAccountAdapter(DefaultAccountAdapter):
    def clean_email(self, email):
        # Normalize email
        email = (email or "").strip().lower()
        if app_settings.UNIQUE_EMAIL:
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError("A user is already registered with this e-mail address.")

        return email