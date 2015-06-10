from django import forms
from django.utils.translation import ugettext as _
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.template import loader, TemplateDoesNotExist
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings


class PasswordResetForm(forms.Form):
    email = forms.EmailField(
        label=_("Email"), max_length=254)

    def save(self, subject_template_name=None, email_template_name=None,
             use_https=False, token_generator=default_token_generator,
             from_email=None, request=None,
             html_email_template_name=None):
        """
        Generates a one-use only link for resetting password and sends to the
        user.
        """
        from django.core.mail import send_mail
        UserModel = get_user_model()
        email = self.cleaned_data["email"]
        active_users = UserModel._default_manager.filter(
            email__iexact=email, is_active=True)
        for user in active_users:
            # Make sure that no email is sent to a user that actually has
            # a password marked as unusable
            if not user.has_usable_password():
                continue
            site_name = domain = request.get_host()

            c = {
                'email': user.email,
                'domain': domain,
                'site_name': site_name,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'user': user,
                'token': token_generator.make_token(user),
                'protocol': 'https' if use_https else 'http',
                'request': request,
                'expiration_days': settings.PASSWORD_RESET_TIMEOUT_DAYS,
            }
            subject = loader.render_to_string(subject_template_name, c)
            # Email subject *must not* contain newlines
            subject = ''.join(subject.splitlines())
            email = loader.render_to_string(email_template_name, c)

            try:
                loader.select_template(html_email_template_name)
            except TemplateDoesNotExist:
                html_email = None
            else:
                html_email = loader.render_to_string(html_email_template_name,
                                                     c)
            send_mail(subject, email, from_email, [user.email],
                      html_message=html_email)