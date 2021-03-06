from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.utils.text import slugify
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.core.validators import RegexValidator

from django_rbac.models import (RoleAbstractBase, PermissionAbstractBase,
                                OrganizationalUnitAbstractBase, RoleParentingAbstractBase, VIEW_OP,
                                CHANGE_OP, Operation)
from django_rbac import utils as rbac_utils

try:
    from django.contrib.contenttypes.fields import GenericForeignKey, \
        GenericRelation
except ImportError:
    # Django < 1.8
    from django.contrib.contenttypes.generic import GenericForeignKey, \
        GenericRelation

from authentic2.decorators import GlobalCache

from . import managers, fields


class OrganizationalUnit(OrganizationalUnitAbstractBase):
    username_is_unique = models.BooleanField(
        blank=True,
        default=False,
        verbose_name=_('Username is unique'))
    email_is_unique = models.BooleanField(
        blank=True,
        default=False,
        verbose_name=_('Email is unique'))
    default = fields.UniqueBooleanField(
        verbose_name=_('Default organizational unit'))

    validate_emails = models.BooleanField(
        blank=True,
        default=False,
        verbose_name=_('Validate emails'))

    admin_perms = GenericRelation(rbac_utils.get_permission_model_name(),
                                  content_type_field='target_ct',
                                  object_id_field='target_id')

    user_can_reset_password = models.NullBooleanField(
        verbose_name=_('Users can reset password'))

    objects = managers.OrganizationalUnitManager()

    class Meta:
        verbose_name = _('organizational unit')
        verbose_name_plural = _('organizational units')
        ordering = ('name',)
        unique_together = (
            ('name',),
            ('slug',),
        )

    def clean(self):
        # if we set this ou as the default one, we must unset the other one if
        # there is
        if self.default:
            qs = self.__class__.objects.filter(default=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            qs.update(default=None)
        if self.pk and not self.default \
           and self.__class__.objects.get(pk=self.pk).default:
            raise ValidationError(_('You cannot unset this organizational '
                                    'unit as the default, but you can set '
                                    'another one as the default.'))
        super(OrganizationalUnit, self).clean()

    def get_admin_role(self):
        '''Get or create the generic admin role for this organizational
           unit.
        '''
        name = _('Managers of "{ou}"').format(ou=self)
        slug = '_a2-managers-of-{ou.slug}'.format(ou=self)
        return Role.objects.get_admin_role(
            instance=self, name=name, slug=slug, operation=VIEW_OP,
            update_name=True, update_slug=True)

    def delete(self, *args, **kwargs):
        Permission.objects.filter(ou=self).delete()
        return super(OrganizationalUnitAbstractBase, self).delete(*args, **kwargs)

    def natural_key(self):
        return [self.slug]

    @classmethod
    @GlobalCache(timeout=5)
    def cached(cls):
        return cls.objects.all()

    def export_json(self):
        return {
            'uuid': self.uuid, 'slug': self.slug, 'name': self.name,
            'description': self.description, 'default': self.default,
            'email_is_unique': self.email_is_unique,
            'username_is_unique': self.username_is_unique,
            'validate_emails': self.validate_emails
        }


OrganizationalUnit._meta.natural_key = [['uuid'], ['slug'], ['name']]


class Permission(PermissionAbstractBase):
    class Meta:
        verbose_name = _('permission')
        verbose_name_plural = _('permissions')

    mirror_roles = GenericRelation(rbac_utils.get_role_model_name(),
                                   content_type_field='admin_scope_ct',
                                   object_id_field='admin_scope_id')


Permission._meta.natural_key = [
    ['operation', 'ou', 'target'],
    ['operation', 'ou__isnull', 'target'],
]


class Role(RoleAbstractBase):
    admin_scope_ct = models.ForeignKey(
        to='contenttypes.ContentType',
        null=True,
        blank=True,
        verbose_name=_('administrative scope content type'))
    admin_scope_id = models.PositiveIntegerField(
        verbose_name=_('administrative scope id'),
        null=True,
        blank=True)
    admin_scope = GenericForeignKey(
        'admin_scope_ct',
        'admin_scope_id')
    service = models.ForeignKey(
        to='authentic2.Service',
        verbose_name=_('service'),
        null=True,
        blank=True,
        related_name='roles')
    external_id = models.TextField(
        verbose_name=_('external id'),
        blank=True,
        db_index=True)

    admin_perms = GenericRelation(rbac_utils.get_permission_model_name(),
                                  content_type_field='target_ct',
                                  object_id_field='target_id')

    def get_admin_role(self, ou=None):
        from . import utils
        admin_role = self.__class__.objects.get_admin_role(
            self, ou=self.ou,
            name=_('Managers of role "{role}"').format(
                role=unicode(self)),
            slug='_a2-managers-of-role-{role}'.format(
                role=slugify(unicode(self))),
            permissions=(utils.get_view_user_perm(),),
            self_administered=True)
        return admin_role

    def clean(self):
        super(Role, self).clean()
        if not self.service and not self.admin_scope_ct_id:
            if not self.id and self.__class__.objects.filter(
                    name=self.name, ou=self.ou):
                raise ValidationError(
                    {'name': _('This name is not unique over this '
                               'organizational unit.')})

    def save(self, *args, **kwargs):
        # Service roles can only be part of the same ou as the service
        if self.service:
            self.ou = self.service.ou
        return super(Role, self).save(*args, **kwargs)

    def has_self_administration(self, op=CHANGE_OP):
        Permission = rbac_utils.get_permission_model()
        admin_op = rbac_utils.get_operation(op)
        self_perm, created = Permission.objects.get_or_create(
            operation=admin_op,
            target_ct=ContentType.objects.get_for_model(self),
            target_id=self.pk)
        return self.permissions.filter(pk=self_perm.pk).exists()

    def add_self_administration(self, op=CHANGE_OP):
        'Add permission to role so that it is self-administered'
        Permission = rbac_utils.get_permission_model()
        admin_op = rbac_utils.get_operation(op)
        self_perm, created = Permission.objects.get_or_create(
            operation=admin_op,
            target_ct=ContentType.objects.get_for_model(self),
            target_id=self.pk)
        self.permissions.through.objects.get_or_create(role=self, permission=self_perm)
        return self_perm

    def is_internal(self):
        return self.slug.startswith('_')

    objects = managers.RoleManager()

    class Meta:
        verbose_name = _('role')
        verbose_name_plural = _('roles')
        ordering = ('ou', 'service', 'name',)
        unique_together = (
            ('admin_scope_ct', 'admin_scope_id'),
        )

    def natural_key(self):
        return [self.slug, self.ou and self.ou.natural_key(), self.service and
                self.service.natural_key()]

    def to_json(self):
        return {
            'uuid': self.uuid,
            'name': self.name,
            'slug': self.slug,
            'is_admin': bool(self.admin_scope_ct and self.admin_scope_id),
            'is_service': bool(self.service),
            'ou__uuid': self.ou.uuid if self.ou else None,
            'ou__name': self.ou.name if self.ou else None,
            'ou__slug': self.ou.slug if self.ou else None,
        }

    def export_json(self, attributes=False, parents=False, permissions=False):
        d = {
            'uuid': self.uuid, 'slug': self.slug, 'name': self.name,
            'description': self.description, 'external_id': self.external_id,
            'ou': self.ou and self.ou.natural_key_json(),
            'service': self.service and self.service.natural_key_json()
        }

        if attributes:
            for attribute in self.attributes.all():
                d.setdefault('attributes', []).append(attribute.to_json())

        if parents:
            RoleParenting = rbac_utils.get_role_parenting_model()
            for parenting in RoleParenting.objects.filter(child_id=self.id, direct=True):
                d.setdefault('parents', []).append(parenting.parent.natural_key_json())

        if permissions:
            for perm in self.permissions.all():
                d.setdefault('permissions', []).append(perm.export_json())

        return d


Role._meta.natural_key = [
    ['uuid'],
    ['slug', 'ou__isnull', 'service__isnull'],
    ['name', 'ou__isnull', 'service__isnull'],
    ['slug', 'ou', 'service'],
    ['name', 'ou', 'service'],
    ['slug', 'ou', 'service__isnull'],
    ['name', 'ou', 'service__isnull'],
]


class RoleParenting(RoleParentingAbstractBase):
    class Meta(RoleParentingAbstractBase.Meta):
        verbose_name = _('role parenting relation')
        verbose_name_plural = _('role parenting relations')


class RoleAttribute(models.Model):
    KINDS = (
        ('string', _('string')),
    )
    role = models.ForeignKey(
        to=Role,
        verbose_name=_('role'),
        related_name='attributes')
    name = models.CharField(
        max_length=64,
        verbose_name=_('name'))
    kind = models.CharField(
        max_length=32,
        choices=KINDS,
        verbose_name=_('kind'))
    value = models.TextField(
        verbose_name=_('value'))

    class Meta:
        verbose_name = ('role attribute')
        verbose_name_plural = _('role attributes')
        unique_together = (
            ('role', 'name', 'kind', 'value'),
        )

    def to_json(self):
        return {'name': self.name, 'kind': self.kind, 'value': self.value}


GenericRelation(Permission,
                content_type_field='target_ct',
                object_id_field='target_id').contribute_to_class(ContentType, 'admin_perms')


CHANGE_PASSWORD_OP = Operation(name=_('Change password'), slug='change_password')
RESET_PASSWORD_OP = Operation(name=_('Reset password'), slug='reset_password')
ACTIVATE_OP = Operation(name=_('Activate'), slug='activate')
CHANGE_EMAIL_OP = Operation(name=_('Change email'), slug='change_email')
