import pytest

from django.contrib.contenttypes.models import ContentType
from django_rbac.utils import get_permission_model
from django_rbac.models import Operation
from authentic2.a2_rbac.models import Role, OrganizationalUnit as OU, RoleAttribute
from authentic2.models import Service
from authentic2.utils import get_hex_uuid


def test_role_natural_key(db):
    ou = OU.objects.create(name='ou1', slug='ou1')
    s1 = Service.objects.create(name='s1', slug='s1')
    s2 = Service.objects.create(name='s2', slug='s2', ou=ou)
    r1 = Role.objects.create(name='r1', slug='r1')
    r2 = Role.objects.create(name='r2', slug='r2', ou=ou)
    r3 = Role.objects.create(name='r3', slug='r3', service=s1)
    r4 = Role.objects.create(name='r4', slug='r4', service=s2)

    for r in (r1, r2, r3, r4):
        assert Role.objects.get_by_natural_key(*r.natural_key()) == r
    assert r1.natural_key() == ['r1', None, None]
    assert r2.natural_key() == ['r2', ['ou1'], None]
    assert r3.natural_key() == ['r3', None, [None, 's1']]
    assert r4.natural_key() == ['r4', ['ou1'], [['ou1'], 's2']]
    ou.delete()
    with pytest.raises(Role.DoesNotExist):
        Role.objects.get_by_natural_key(*r2.natural_key())
    with pytest.raises(Role.DoesNotExist):
        Role.objects.get_by_natural_key(*r4.natural_key())


def test_basic_role_export_json(db):
    role = Role.objects.create(
        name='basic role', slug='basic-role', description='basic role description')
    role_dict = role.export_json()
    assert role_dict['name'] == role.name
    assert role_dict['slug'] == role.slug
    assert role_dict['uuid'] == role.uuid
    assert role_dict['description'] == role.description
    assert role_dict['external_id'] == role.external_id
    assert role_dict['ou'] is None
    assert role_dict['service'] is None


def test_role_with_ou_export_json(db):
    ou = OU.objects.create(name='ou', slug='ou')
    role = Role.objects.create(name='some role', ou=ou)
    role_dict = role.export_json()
    assert role_dict['ou'] == {'uuid': ou.uuid, 'slug': ou.slug,  'name': ou.name}


def test_role_with_service_export_json(db):
    service = Service.objects.create(name='service name', slug='service-name')
    role = Role.objects.create(name='some role', service=service)
    role_dict = role.export_json()
    assert role_dict['service'] == {'slug': service.slug,  'ou': None}


def test_role_with_service_with_ou_export_json(db):
    ou = OU.objects.create(name='ou', slug='ou')
    service = Service.objects.create(name='service name', slug='service-name', ou=ou)
    role = Role.objects.create(name='some role', service=service)
    role_dict = role.export_json()
    assert role_dict['service'] == {
        'slug': service.slug,  'ou': {'uuid': ou.uuid, 'slug': 'ou', 'name': 'ou'}}


def test_role_with_attributes_export_json(db):
    role = Role.objects.create(name='some role')
    attr1 = RoleAttribute.objects.create(
        role=role, name='attr1_name', kind='string', value='attr1_value')
    attr2 = RoleAttribute.objects.create(
        role=role, name='attr2_name', kind='string', value='attr2_value')

    role_dict = role.export_json(attributes=True)
    attributes = role_dict['attributes']
    assert len(attributes) == 2

    expected_attr_names = set([attr1.name, attr2.name])
    for attr_dict in attributes:
        assert attr_dict['name'] in expected_attr_names
        expected_attr_names.remove(attr_dict['name'])
        target_attr = RoleAttribute.objects.filter(name=attr_dict['name']).first()
        assert attr_dict['kind'] == target_attr.kind
        assert attr_dict['value'] == target_attr.value


def test_role_with_parents_export_json(db):
    grand_parent_role = Role.objects.create(
        name='test grand parent role', slug='test-grand-parent-role')
    parent_1_role = Role.objects.create(
        name='test parent 1 role', slug='test-parent-1-role')
    parent_1_role.add_parent(grand_parent_role)
    parent_2_role = Role.objects.create(
        name='test parent 2 role', slug='test-parent-2-role')
    parent_2_role.add_parent(grand_parent_role)
    child_role = Role.objects.create(
        name='test child role', slug='test-child-role')
    child_role.add_parent(parent_1_role)
    child_role.add_parent(parent_2_role)

    child_role_dict = child_role.export_json(parents=True)
    assert child_role_dict['slug'] == child_role.slug
    parents = child_role_dict['parents']
    assert len(parents) == 2
    expected_slugs = set([parent_1_role.slug, parent_2_role.slug])
    for parent in parents:
        assert parent['slug'] in expected_slugs
        expected_slugs.remove(parent['slug'])

    grand_parent_role_dict = grand_parent_role.export_json(parents=True)
    assert grand_parent_role_dict['slug'] == grand_parent_role.slug
    assert 'parents' not in grand_parent_role_dict

    parent_1_role_dict = parent_1_role.export_json(parents=True)
    assert parent_1_role_dict['slug'] == parent_1_role.slug
    parents = parent_1_role_dict['parents']
    assert len(parents) == 1
    assert parents[0]['slug'] == grand_parent_role.slug

    parent_2_role_dict = parent_2_role.export_json(parents=True)
    assert parent_2_role_dict['slug'] == parent_2_role.slug
    parents = parent_2_role_dict['parents']
    assert len(parents) == 1
    assert parents[0]['slug'] == grand_parent_role.slug


def test_role_with_permission_export_json(db):
    some_ou = OU.objects.create(name='some ou', slug='some-ou')
    role = Role.objects.create(name='role name', slug='role-slug')
    other_role = Role.objects.create(
        name='other role name', slug='other-role-slug', uuid=get_hex_uuid(), ou=some_ou)
    ou = OU.objects.create(name='basic ou', slug='basic-ou', description='basic ou description')
    Permission = get_permission_model()
    op = Operation.objects.first()
    perm_saml = Permission.objects.create(
        operation=op, ou=ou,
        target_ct=ContentType.objects.get_for_model(ContentType),
        target_id=ContentType.objects.get(app_label="saml", model="libertyprovider").pk)
    role.permissions.add(perm_saml)
    perm_role = Permission.objects.create(
        operation=op, ou=None,
        target_ct=ContentType.objects.get_for_model(Role),
        target_id=other_role.pk)
    role.permissions.add(perm_role)

    export = role.export_json(permissions=True)
    permissions = export['permissions']
    assert len(permissions) == 2
    assert permissions[0] == {
        'operation': {'slug': 'add'},
        'ou': {'uuid': ou.uuid, 'slug': ou.slug, 'name': ou.name},
        'target_ct': {'app_label': u'contenttypes', 'model': u'contenttype'},
        'target': {'model': u'libertyprovider', 'app_label': u'saml'}
    }
    assert permissions[1] == {
        'operation': {'slug': 'add'},
        'ou': None,
        'target_ct': {'app_label': u'a2_rbac', 'model': u'role'},
        'target': {
            'slug': u'other-role-slug', 'service': None, 'uuid': other_role.uuid,
            'ou': {
                'slug': u'some-ou', 'uuid': some_ou.uuid, 'name': u'some ou'
            },
            'name': u'other role name'}
    }


def test_ou_export_json(db):
    ou = OU.objects.create(
        name='basic ou', slug='basic-ou', description='basic ou description',
        username_is_unique=True, email_is_unique=True, default=False, validate_emails=True)
    ou_dict = ou.export_json()
    assert ou_dict['name'] == ou.name
    assert ou_dict['slug'] == ou.slug
    assert ou_dict['uuid'] == ou.uuid
    assert ou_dict['description'] == ou.description
    assert ou_dict['username_is_unique'] == ou.username_is_unique
    assert ou_dict['email_is_unique'] == ou.email_is_unique
    assert ou_dict['default'] == ou.default
    assert ou_dict['validate_emails'] == ou.validate_emails
