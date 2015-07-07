from django.utils.translation import ugettext as _
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType

from django_rbac.utils import get_role_model, get_ou_model, \
    get_permission_model

from ..utils import get_fk_model
from . import utils, app_settings


def update_ou_admin_roles(ou):
    Role = get_role_model()

    if app_settings.MANAGED_CONTENT_TYPES == ():
        Role.objects.filter(slug='a2-managers-of-{ou.slug}'.format(ou=ou)) \
            .delete()
    else:
        ou_admin_role = ou.get_admin_role()

    for key in MANAGED_CT:
        ct = ContentType.objects.get_by_natural_key(key[0], key[1])
        model_class = ct.model_class()
        ou_model = get_fk_model(model_class, 'ou')
        # do not create scoped admin roles if the model is not scopable
        if not ou_model:
            continue
        name = MANAGED_CT[key]['name']
        slug = '_a2-' + slugify(name)
        scoped_name = MANAGED_CT[key]['scoped_name']
        name = scoped_name.format(ou=ou)
        ou_slug = slug + '-' + ou.slug
        if app_settings.MANAGED_CONTENT_TYPES == ():
            Role.objects.filter(slug=ou_slug, ou=ou).delete()
            continue
        else:
            ou_ct_admin_role = Role.objects.get_admin_role(
                instance=ct,
                ou=ou,
                name=name,
                slug=ou_slug,
                update_slug=True,
                update_name=True)
        if not app_settings.MANAGED_CONTENT_TYPES or \
               key in app_settings.MANAGED_CONTENT_TYPES:
            ou_ct_admin_role.add_child(ou_admin_role)
        else:
            ou_ct_admin_role.remove_child(ou_admin_role)
        if MANAGED_CT[key].get('must_view_user'):
            ou_ct_admin_role.permissions.add(utils.get_view_user_perm(ou))


def update_ous_admin_roles():
    '''Create general admin roles linked to all organizational units,
       they give general administrative rights to all mamanged content types
       scoped to the given organizational unit.
    '''
    Permission = get_permission_model()
    OU = get_ou_model()
    ou_all = OU.objects.all()
    ou_ids = ou_all.values_list('id', flat=True)
    ou_ids_with_perm = Permission.objects.filter(
        operation__slug='admin',
        target_ct=ContentType.objects.get_for_model(OU)) \
        .values_list('target_id', flat=True)

    for ou in OU.objects.filter(id__in=set(ou_ids)-set(ou_ids_with_perm)):
        update_ou_admin_roles(ou)

MANAGED_CT = {
    ('authentic2', 'service'): {
        'name': _('Manager of services'),
        'scoped_name': _('Services - {ou}'),
    },
    ('a2_rbac', 'role'): {
        'name': _('Manager of roles'),
        'scoped_name': _('Roles - {ou}'),
        'must_view_user': True,
    },
    ('a2_rbac', 'organizationalunit'): {
        'name': _('Manager of organizational units'),
        'scoped_name': _('Organizational unit - {ou}'),
    },
    ('custom_user', 'user'): {
        'name': _('Manager of users'),
        'scoped_name': _('Users - {ou}'),
    },
}


def update_content_types_roles():
    '''Create general and scoped management roles for all managed content
       types.
    '''
    cts = ContentType.objects.all()
    Role = get_role_model()
    view_user_perm = utils.get_view_user_perm()
    slug='_a2-manager'
    if app_settings.MANAGED_CONTENT_TYPES == ():
        Role.objects.filter(slug=slug).delete()
    else:
        admin_role, created = Role.objects.get_or_create(
            slug=slug,
            defaults=dict(
                name=_('Manager')))
        admin_role.add_self_administration()
        if not created and admin_role.name != _('Manager'):
            admin_role.name = _('Manager')
            admin_role.save()

    for ct in cts:
        ct_tuple = (ct.app_label.lower(), ct.model.lower())
        if ct_tuple not in MANAGED_CT:
            continue
        # General admin role
        name = MANAGED_CT[ct_tuple]['name']
        slug = '_a2-' + slugify(name)
        if not app_settings.MANAGED_CONTENT_TYPES is None and key not in \
                app_settings.MANAGED_CONTENT_TYPES:
            Role.objects.filter(slug=slug).delete()
            continue
        ct_admin_role = Role.objects.get_admin_role(instance=ct, name=name,
                                                    slug=slug,
                                                    update_name=True)
        if MANAGED_CT[ct_tuple].get('must_view_user'):
            ct_admin_role.permissions.add(utils.get_view_user_perm())
        ct_admin_role.add_child(admin_role)
