from django.utils.http import urlquote
from django.db import models
from django.utils import timezone
from django.core.mail import send_mail
from django.contrib.auth.models import AbstractBaseUser
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError

from django_rbac.backends import DjangoRBACBackend
from django_rbac.models import PermissionMixin
from django_rbac.utils import get_role_parenting_model

from authentic2 import utils, validators, app_settings
from authentic2.decorators import errorcollector

from .managers import UserManager

class User(AbstractBaseUser, PermissionMixin):
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
    ou = models.ForeignKey(
        verbose_name=_('organizational unit'),
        to='a2_rbac.OrganizationalUnit',
        blank=True,
        null=True,
        swappable=False)


    objects = UserManager()

    USERNAME_FIELD = 'uuid'
    REQUIRED_FIELDS = ['username', 'email']
    USER_PROFILE = ('first_name', 'last_name', 'email')

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        permissions = (
            ('view_user', 'can see available users'),
        )

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
        return self.username or self.email or self.get_full_name() or self.uuid

    def roles_and_parents(self):
        qs1 = self.roles.all().extra(select={'member': 'a2_rbac_role_members.id is not null'})
        qs2 = qs1.model.objects.filter(child_relation__child=qs1)
        qs = (qs1 | qs2).order_by('name').distinct()
        RoleParenting = get_role_parenting_model()
        rp_qs = RoleParenting.objects.filter(child=qs1)
        qs = qs.prefetch_related(models.Prefetch(
            'child_relation', queryset=rp_qs), 'child_relation__parent')
        return qs

    def __unicode__(self):
        human_name = self.username or self.get_full_name() or self.email
        short_id = self.uuid[:6]
        return u'%s (%s)' % (human_name, short_id)

    def clean(self):
        errors = {}
        with errorcollector(errors):
            super(User, self).clean()

        model = self.__class__
        qs = model.objects
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if self.ou_id:
            qs = qs.filter(ou_id=self.ou_id)
        else:
            qs = qs.filter(ou__isnull=True)
        if self.username and app_settings.A2_USERNAME_IS_UNIQUE:
            try:
                qs.get(username=self.username)
            except model.DoesNotExist:
                pass
            else:
                errors['username'] = _('This username is already in '
                                        'use. Please supply a different username.')
        if self.email and app_settings.A2_EMAIL_IS_UNIQUE:
            try:
                qs.get(email__iexact=self.email)
            except model.DoesNotExist:
                pass
            else:
                errors['email'] = _('This email address is already in '
                                        'use. Please supply a different email address.')
        if errors:
            raise ValidationError(errors)

    def natural_key(self):
        return (self.uuid,)

User._meta.get_field('last_login').null = True
User._meta.get_field('last_login').blank = True

