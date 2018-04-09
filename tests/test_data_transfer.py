import json

from django_rbac.utils import get_role_model, get_ou_model
import py
import pytest

from authentic2.a2_rbac.models import RoleParenting
from authentic2.data_transfer import (
    DataImportError, export_roles, import_site, export_ou, ImportContext,
    RoleDeserializer, search_role, import_ou)
from authentic2.utils import get_hex_uuid


Role = get_role_model()
OU = get_ou_model()


def test_export_basic_role(db):
    role = Role.objects.create(name='basic role', slug='basic-role', uuid=get_hex_uuid())
    query_set = Role.objects.filter(uuid=role.uuid)
    roles = export_roles(query_set)
    assert len(roles) == 1
    role_dict = roles[0]
    for key, value in role.export_json().items():
        assert role_dict[key] == value


def test_export_role_with_parents(db):
    grand_parent_role = Role.objects.create(
        name='test grand parent role', slug='test-grand-parent-role', uuid=get_hex_uuid())
    parent_1_role = Role.objects.create(
        name='test parent 1 role', slug='test-parent-1-role', uuid=get_hex_uuid())
    parent_1_role.add_parent(grand_parent_role)
    parent_2_role = Role.objects.create(
        name='test parent 2 role', slug='test-parent-2-role', uuid=get_hex_uuid())
    parent_2_role.add_parent(grand_parent_role)
    child_role = Role.objects.create(
        name='test child role', slug='test-child-role', uuid=get_hex_uuid())
    child_role.add_parent(parent_1_role)
    child_role.add_parent(parent_2_role)

    query_set = Role.objects.filter(slug__startswith='test').order_by('slug')
    roles = export_roles(query_set)
    assert len(roles) == 4

    child_role_dict = roles[0]
    assert child_role_dict['slug'] == child_role.slug
    parents = child_role_dict['parents']
    assert len(parents) == 2
    expected_slugs = set([parent_1_role.slug, parent_2_role.slug])
    for parent in parents:
        assert parent['slug'] in expected_slugs
        expected_slugs.remove(parent['slug'])

    grand_parent_role_dict = roles[1]
    assert grand_parent_role_dict['slug'] == grand_parent_role.slug

    parent_1_role_dict = roles[2]
    assert parent_1_role_dict['slug'] == parent_1_role.slug
    parents = parent_1_role_dict['parents']
    assert len(parents) == 1
    assert parents[0]['slug'] == grand_parent_role.slug

    parent_2_role_dict = roles[3]
    assert parent_2_role_dict['slug'] == parent_2_role.slug
    parents = parent_2_role_dict['parents']
    assert len(parents) == 1
    assert parents[0]['slug'] == grand_parent_role.slug


def test_export_ou(db):
    ou = OU.objects.create(name='ou name', slug='ou-slug', description='ou description')
    ous = export_ou(OU.objects.filter(name='ou name'))
    assert len(ous) == 1
    ou_d = ous[0]
    assert ou_d['name'] == ou.name
    assert ou_d['slug'] == ou.slug
    assert ou_d['description'] == ou.description


def test_search_role_by_uuid(db):
    uuid = get_hex_uuid()
    role_d = {'uuid': uuid, 'slug': 'role-slug'}
    role = Role.objects.create(**role_d)
    assert role == search_role({'uuid': uuid, 'slug': 'other-role-slug'})


def test_search_role_by_slug(db):
    role_d = {'uuid': get_hex_uuid(), 'slug': 'role-slug'}
    role = Role.objects.create(**role_d)
    assert role == search_role({
        'uuid': get_hex_uuid(), 'slug': 'role-slug',
        'ou': None, 'service': None})


def test_search_role_not_found(db):
    assert search_role(
        {
            'uuid': get_hex_uuid(), 'slug': 'role-slug', 'name': 'role name',
            'ou': None, 'service': None}) is None


def test_search_role_slug_not_unique(db):
    role1_d = {'uuid': get_hex_uuid(), 'slug': 'role-slug', 'name': 'role name'}
    role2_d = {'uuid': get_hex_uuid(), 'slug': 'role-slug', 'name': 'role name'}
    ou = OU.objects.create(name='some ou', slug='some-ou')
    role1 = Role.objects.create(ou=ou, **role1_d)
    Role.objects.create(**role2_d)
    assert role1 == search_role(role1.export_json())


def test_role_deserializer(db):
    rd = RoleDeserializer({
        'name': 'some role', 'description': 'some role description', 'slug': 'some-role',
        'uuid': get_hex_uuid(), 'ou': None, 'service': None}, ImportContext())
    assert rd._parents is None
    assert rd._attributes is None
    assert rd._obj is None
    role, status = rd.deserialize()
    assert status == 'created'
    assert role.name == 'some role'
    assert role.description == 'some role description'
    assert role.slug == 'some-role'
    assert rd._obj == role


def test_role_deserializer_with_ou(db):
    ou = OU.objects.create(name='some ou', slug='some-ou')
    rd = RoleDeserializer({
        'uuid': get_hex_uuid(), 'name': 'some role', 'description': 'some role description',
        'slug': 'some-role', 'ou': {'slug': 'some-ou'}, 'service': None}, ImportContext())
    role, status = rd.deserialize()
    assert role.ou == ou


def test_role_deserializer_missing_ou(db):
    rd = RoleDeserializer({
        'uuid': get_hex_uuid(), 'name': 'some role', 'description': 'role description',
        'slug': 'some-role', 'ou': {'slug': 'some-ou'}, 'service': None},
            ImportContext())
    with pytest.raises(DataImportError):
        rd.deserialize()


def test_role_deserializer_update_ou(db):
    ou1 = OU.objects.create(name='ou 1', slug='ou-1')
    ou2 = OU.objects.create(name='ou 2', slug='ou-2')
    uuid = get_hex_uuid()
    existing_role = Role.objects.create(uuid=uuid, slug='some-role', ou=ou1)
    rd = RoleDeserializer({
        'uuid': uuid, 'name': 'some-role', 'slug': 'some-role',
        'ou': {'slug': 'ou-2'}, 'service': None}, ImportContext())
    role, status = rd.deserialize()
    assert role == existing_role
    assert role.ou == ou2


def test_role_deserializer_update_fields(db):
    uuid = get_hex_uuid()
    existing_role = Role.objects.create(uuid=uuid, slug='some-role', name='some role')
    rd = RoleDeserializer({
        'uuid': uuid, 'slug': 'some-role', 'name': 'some role changed',
        'ou': None, 'service': None}, ImportContext())
    role, status = rd.deserialize()
    assert role == existing_role
    assert role.name == 'some role changed'


def test_role_deserializer_with_attributes(db):

    attributes_data = {
        'attr1_name': dict(name='attr1_name', kind='string', value='attr1_value'),
        'attr2_name': dict(name='attr2_name', kind='string', value='attr2_value')
    }
    rd = RoleDeserializer({
        'uuid': get_hex_uuid(), 'name': 'some role', 'description': 'some role description',
        'slug': 'some-role', 'attributes': list(attributes_data.values()),
        'ou': None, 'service': None}, ImportContext())
    role, status = rd.deserialize()
    created, deleted = rd.attributes()
    assert role.attributes.count() == 2
    assert len(created) == 2

    for attr in created:
        attr_dict = attributes_data[attr.name]
        assert attr_dict['name'] == attr.name
        assert attr_dict['kind'] == attr.kind
        assert attr_dict['value'] == attr.value
        del attributes_data[attr.name]


def test_role_deserializer_creates_admin_role(db):
    role_dict = {
        'name': 'some role', 'slug': 'some-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    rd = RoleDeserializer(role_dict, ImportContext())
    rd.deserialize()
    Role.objects.get(slug='_a2-managers-of-role-some-role')


def test_role_deserializer_parenting_existing_parent(db):
    parent_role_dict = {
        'name': 'grand parent role', 'slug': 'grand-parent-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    parent_role = Role.objects.create(**parent_role_dict)
    child_role_dict = {
        'name': 'child role', 'slug': 'child-role', 'parents': [parent_role_dict],
        'uuid': get_hex_uuid(), 'ou': None, 'service': None}

    rd = RoleDeserializer(child_role_dict, ImportContext())
    child_role, status = rd.deserialize()
    created, deleted = rd.parentings()

    assert len(created) == 1
    parenting = created[0]
    assert parenting.direct is True
    assert parenting.parent == parent_role
    assert parenting.child == child_role


def test_role_deserializer_parenting_non_existing_parent(db):
    parent_role_dict = {
        'name': 'grand parent role', 'slug': 'grand-parent-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    child_role_dict = {
        'name': 'child role', 'slug': 'child-role', 'parents': [parent_role_dict],
        'uuid': get_hex_uuid(), 'ou': None, 'service': None}
    rd = RoleDeserializer(child_role_dict, ImportContext())
    rd.deserialize()
    with pytest.raises(DataImportError) as excinfo:
        rd.parentings()

    assert "Could not find role" in str(excinfo.value)


def test_role_deserializer_permissions(db):
    ou = OU.objects.create(slug='some-ou')
    other_role_dict = {
        'name': 'other role', 'slug': 'other-role-slug', 'uuid': get_hex_uuid(), 'ou': ou}
    other_role = Role.objects.create(**other_role_dict)
    other_role_dict['permisison'] = {
        "operation": {
            "slug": "admin"
        },
        "ou": {
            "slug": "default",
            "name": "Collectivit\u00e9 par d\u00e9faut"
        },
        'target_ct': {'app_label': u'a2_rbac', 'model': u'role'},
        "target": {
            "slug": "role-deux",
            "ou": {
                "slug": "default",
                "name": "Collectivit\u00e9 par d\u00e9faut"
            },
            "service": None,
            "name": "role deux"
        }
    }
    some_role_dict = {
        'name': 'some role', 'slug': 'some-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    some_role_dict['permissions'] = [
        {
            'operation': {'slug': 'add'},
            'ou': None,
            'target_ct': {'app_label': u'a2_rbac', 'model': u'role'},
            'target': {
                "slug": u'other-role-slug', 'ou': {'slug': 'some-ou'}, 'service': None}
        }
    ]

    import_context = ImportContext()
    rd = RoleDeserializer(some_role_dict, import_context)
    rd.deserialize()
    perm_created, perm_deleted = rd.permissions()

    assert len(perm_created) == 1
    assert len(perm_deleted) == 0
    del some_role_dict['permissions']
    role = Role.objects.get(slug=some_role_dict['slug'])
    assert role.permissions.count() == 1
    perm = role.permissions.first()
    assert perm.operation.slug == 'add'
    assert not perm.ou
    assert perm.target == other_role

    # that one should delete permissions
    rd = RoleDeserializer(some_role_dict, import_context)
    role, _ = rd.deserialize()
    perm_created, perm_deleted = rd.permissions()
    assert role.permissions.count() == 0
    assert len(perm_created) == 0
    assert len(perm_deleted) == 1


def test_permission_on_role(db):
    perm_ou = OU.objects.create(slug='perm-ou', name='perm ou')
    perm_role = Role.objects.create(slug='perm-role', ou=perm_ou, name='perm role')

    some_role_dict = {
        'name': 'some role', 'slug': 'some-role-slug', 'ou': None, 'service': None}
    some_role_dict['permissions'] = [{
        "operation": {
            "slug": "admin"
        },
        "ou": {
            "slug": "perm-ou",
            "name": "perm-ou"
        },
        'target_ct': {'app_label': u'a2_rbac', 'model': u'role'},
        "target": {
            "slug": "perm-role",
            "ou": {
                "slug": "perm-ou",
                "name": "perm ou"
            },
            "service": None,
            "name": "perm role"
        }
    }]

    import_context = ImportContext()
    rd = RoleDeserializer(some_role_dict, import_context)
    rd.deserialize()
    perm_created, perm_deleted = rd.permissions()
    assert len(perm_created) == 1
    perm = perm_created[0]
    assert perm.target == perm_role
    assert perm.ou == perm_ou
    assert perm.operation.slug == 'admin'


def test_permission_on_contentype(db):
    perm_ou = OU.objects.create(slug='perm-ou', name='perm ou')
    some_role_dict = {
        'name': 'some role', 'slug': 'some-role-slug', 'ou': None, 'service': None}
    some_role_dict['permissions'] = [{
        "operation": {
            "slug": "admin"
        },
        "ou": {
            "slug": "perm-ou",
            "name": "perm-ou"
        },
        'target_ct': {"model": "contenttype", "app_label": "contenttypes"},
        "target": {"model": "logentry", "app_label": "admin"}
    }]

    import_context = ImportContext()
    rd = RoleDeserializer(some_role_dict, import_context)
    rd.deserialize()
    perm_created, perm_deleted = rd.permissions()
    assert len(perm_created) == 1
    perm = perm_created[0]
    assert perm.target.app_label == 'admin'
    assert perm.target.model == 'logentry'
    assert perm.ou == perm_ou


def import_ou_created(db):
    uuid = get_hex_uuid()
    ou_d = {'uuid': uuid, 'slug': 'ou-slug', 'name': 'ou name'}
    ou, status = import_ou(ou_d)
    assert status == 'created'
    assert ou.uuid == ou_d['uuid']
    assert ou.slug == ou_d['slug']
    assert ou.name == ou_d['name']


def import_ou_updated(db):
    ou = OU.objects.create(slug='some-ou', name='ou name')
    ou_d = {'uuid': ou.uuid, 'slug': ou.slug, 'name': 'new name'}
    ou_updated, status = import_ou(ou_d)
    assert status == 'updated'
    assert ou == ou_updated
    assert ou.name == 'new name'


def testi_import_site_empty():
    res = import_site({}, ImportContext())
    assert res.roles == {'created': [], 'updated': []}
    assert res.ous == {'created': [], 'updated': []}
    assert res.parentings == {'created': [], 'deleted': []}


def test_import_site_roles(db):
    parent_role_dict = {
        'name': 'grand parent role', 'slug': 'grand-parent-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    child_role_dict = {
        'name': 'child role', 'slug': 'child-role', 'parents': [parent_role_dict],
        'uuid': get_hex_uuid(), 'ou': None, 'service': None}
    roles = [
        parent_role_dict,
        child_role_dict
    ]
    res = import_site({'roles': roles}, ImportContext())
    created_roles = res.roles['created']
    assert len(created_roles) == 2
    parent_role = Role.objects.get(**parent_role_dict)
    del child_role_dict['parents']
    child_role = Role.objects.get(**child_role_dict)
    assert created_roles[0] == parent_role
    assert created_roles[1] == child_role

    assert len(res.parentings['created']) == 1
    assert res.parentings['created'][0] == RoleParenting.objects.get(
        child=child_role, parent=parent_role, direct=True)


def test_roles_import_ignore_technical_role(db):
    roles = [{
        'name': 'some role', 'description': 'some role description', 'slug': '_some-role'}]
    res = import_site({'roles': roles}, ImportContext())
    assert res.roles == {'created': [], 'updated': []}


def test_roles_import_ignore_technical_role_with_service(db):
    roles = [{
        'name': 'some role', 'description': 'some role description', 'slug': '_some-role'}]
    res = import_site({'roles': roles}, ImportContext())
    assert res.roles == {'created': [], 'updated': []}


def test_import_role_handle_manager_role_parenting(db):
    parent_role_dict = {
        'name': 'grand parent role', 'slug': 'grand-parent-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    parent_role_manager_dict = {
        'name': 'Administrateur du role grand parent role',
        'slug': '_a2-managers-of-role-grand-parent-role', 'uuid': get_hex_uuid(),
        'ou': None, 'service': None}
    child_role_dict = {
        'name': 'child role', 'slug': 'child-role',
        'parents': [parent_role_dict, parent_role_manager_dict],
        'uuid': get_hex_uuid(), 'ou': None, 'service': None}
    import_site({'roles': [child_role_dict, parent_role_dict]}, ImportContext())
    child = Role.objects.get(slug='child-role')
    manager = Role.objects.get(slug='_a2-managers-of-role-grand-parent-role')
    RoleParenting.objects.get(child=child, parent=manager, direct=True)


def test_import_roles_role_delete_orphans(db):
    roles = [{
        'name': 'some role', 'description': 'some role description', 'slug': '_some-role'}]
    with pytest.raises(DataImportError):
        import_site({'roles': roles}, ImportContext(role_delete_orphans=True))


def test_import_ou(db):
    uuid = get_hex_uuid()
    name = 'ou name'
    ous = [{'uuid': uuid, 'slug': 'ou-slug', 'name': name}]
    res = import_site({'ous': ous}, ImportContext())
    assert len(res.ous['created']) == 1
    ou = res.ous['created'][0]
    assert ou.uuid == uuid
    assert ou.name == name
    Role.objects.get(slug='_a2-managers-of-ou-slug')


def test_import_ou_already_existing(db):
    uuid = get_hex_uuid()
    ou_d = {'uuid': uuid, 'slug': 'ou-slug', 'name': 'ou name'}
    ou = OU.objects.create(**ou_d)
    num_ous = OU.objects.count()
    res = import_site({'ous': [ou_d]}, ImportContext())
    assert len(res.ous['created']) == 0
    assert num_ous == OU.objects.count()
    assert ou == OU.objects.get(uuid=uuid)
