
from django import forms
from django.utils.translation import ugettext as _
from django.contrib.auth import get_user_model

from .backends import get_user_queryset
from .utils import send_password_reset_mail
from . import hooks, app_settings


class PasswordResetForm(forms.Form):
    next_url = forms.CharField(widget=forms.HiddenInput, required=False)

    email = forms.EmailField(
        label=_("Email"), max_length=254)

    def save(self):
        """
        Generates a one-use only link for resetting password and sends to the
        user.
        """
        email = self.cleaned_data["email"].strip()
        users = get_user_queryset()
        active_users = users.filter(email__iexact=email, is_active=True)
        for user in active_users:
            # we don't set the password to a random string, as some users should not have
            # a password
            set_random_password = (user.has_usable_password()
                                   and app_settings.A2_SET_RANDOM_PASSWORD_ON_RESET)
            send_password_reset_mail(user, set_random_password=set_random_password,
                                     next_url=self.cleaned_data.get('next_url'))
        hooks.call_hooks('event', name='password-reset', email=email, users=active_users)
