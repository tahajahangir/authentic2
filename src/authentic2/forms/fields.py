from django.forms import CharField
from django.utils.translation import ugettext_lazy as _

from authentic2.passwords import password_help_text, validate_password
from authentic2.forms.widgets import PasswordInput, NewPasswordInput, CheckPasswordInput


class PasswordField(CharField):
    widget = PasswordInput


class NewPasswordField(CharField):
    widget = NewPasswordInput
    default_validators = [validate_password]

    def __init__(self, *args, **kwargs):
        kwargs['help_text'] = password_help_text()
        super(NewPasswordField, self).__init__(*args, **kwargs)


class CheckPasswordField(CharField):
    widget = CheckPasswordInput

    def __init__(self, *args, **kwargs):
        kwargs['help_text'] = u'''
    <span class="a2-password-check-equality-default">%(default)s</span>
    <span class="a2-password-check-equality-matched">%(match)s</span>
    <span class="a2-password-check-equality-unmatched">%(nomatch)s</span>
''' % {
            'default': _('Both passwords must match.'),
            'match': _('Passwords match.'),
            'nomatch': _('Passwords do not match.'),
        }
        super(CheckPasswordField, self).__init__(*args, **kwargs)

