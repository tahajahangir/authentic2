from django.utils.http import urlquote
from django.db import models
from django.utils import timezone
from django.core.mail import send_mail
from django.contrib.auth.models import (AbstractBaseUser, PermissionsMixin)
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError

from authentic2 import utils, validators, app_settings

from .managers import UserManager

class User(AbstractBaseUser, PermissionsMixin):
    """
    An abstract base class implementing a fully featured User model with
    admin-compliant permissions.

    Username, password and email are required. Other fields are optional.
    """
    uuid = models.CharField(_('uuid'), max_length=32,
            default=utils.get_hex_uuid, editable=False, unique=True)
    username = models.CharField(_('username'), max_length=256, null=True, blank=True)
    first_name = models.CharField(_('first name'), max_length=64, blank=True)
    last_name = models.CharField(_('last name'), max_length=64, blank=True)
    email = models.EmailField(_('email address'), blank=True,
            validators=[validators.EmailValidator], max_length=254)
    is_staff = models.BooleanField(_('staff status'), default=False,
        help_text=_('Designates whether the user can log into this admin '
                    'site.'))
    is_active = models.BooleanField(_('active'), default=True,
        help_text=_('Designates whether this user should be treated as '
                    'active. Unselect this instead of deleting accounts.'))
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'uuid'
    REQUIRED_FIELDS = ['username', 'email']
    USER_PROFILE = ('first_name', 'last_name', 'email')

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip() or self.username or self.email

    def get_short_name(self):
        "Returns the short name for the user."
        return self.first_name or self.username or self.email or self.uuid[:6]

    def email_user(self, subject, message, from_email=None):
        """
        Sends an email to this User.
        """
        send_mail(subject, message, from_email, [self.email])

    def get_username(self):
        "Return the identifying username for this User"
        return self.username or self.get_full_name() or self.uuid

    def __unicode__(self):
        human_name = self.username or self.get_full_name() or self.email
        short_id = self.uuid[:6]
        return u'%s (%s)' % (human_name, short_id)

    def clean(self):
        super(User, self).clean()
        errors = {}
        if self.username and app_settings.A2_USERNAME_IS_UNIQUE:
            try:
                self.__class__.objects.exclude(id=self.id).get(username=self.username)
            except self.__class__.DoesNotExist:
                pass
            else:
                errors['username'] = _('This username is already in '
                                        'use. Please supply a different username.')
        if self.email and app_settings.A2_EMAIL_IS_UNIQUE:
            try:
                self.__class__.objects.exclude(id=self.id).get(email__iexact=self.email)
            except self.__class__.DoesNotExist:
                pass
            else:
                errors['email'] = _('This email address is already in '
                                        'use. Please supply a different email address.')
        if errors:
            raise ValidationError(errors)

    def natural_key(self):
        return (self.uuid,)

