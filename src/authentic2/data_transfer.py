from django.contrib.contenttypes.models import ContentType

from django_rbac.models import Operation
from django_rbac.utils import (
    get_ou_model,  get_role_model, get_role_parenting_model, get_permission_model)
from authentic2.a2_rbac.models import RoleAttribute
from authentic2.utils import update_model


def export_site():
    return {
        'roles': export_roles(get_role_model().objects.all()),
        'ous': export_ou(get_ou_model().objects.all())
    }


def export_ou(ou_query_set):
    return [ou.export_json() for ou in ou_query_set]


def export_roles(role_queryset):
    """ Serialize roles in role_queryset
    """
    return [
        role.export_json(attributes=True, parents=True, permissions=True)
        for role in role_queryset
    ]


def search_ou(ou_d):
    try:
        OU = get_ou_model()
        return OU.objects.get_by_natural_key_json(ou_d)
    except OU.DoesNotExist:
        return None


def search_role(role_d):
    Role = get_role_model()
    try:
        Role = get_role_model()
        return Role.objects.get_by_natural_key_json(role_d)
    except Role.DoesNotExist:
        return None


class ImportContext(object):
    """ Holds information on how to perform the import.

    ou_delete_orphans: if True any existing ou that is not found in the export will
                       be deleted

    role_delete_orphans: if True any existing role that is not found in the export will
                         be deleted


    role_attributes_update: for each role in the import data,
                            attributes  will deleted and re-created


    role_parentings_update: for each role in the import data,
                            parentings will deleted and re-created

    role_permissions_update: for each role in the import data,
                             permissions  will deleted and re-created
    """

    def __init__(
            self, role_delete_orphans=False, role_parentings_update=True,
            role_permissions_update=True, role_attributes_update=True,
            ou_delete_orphans=False):
        self.role_delete_orphans = role_delete_orphans
        self.ou_delete_orphans = ou_delete_orphans
        self.role_parentings_update = role_parentings_update
        self.role_permissions_update = role_permissions_update
        self.role_attributes_update = role_attributes_update


class DataImportError(Exception):
    pass


class RoleDeserializer(object):

    def __init__(self, d, import_context):
        self._import_context = import_context
        self._obj = None
        self._parents = None
        self._attributes = None
        self._permissions = None

        self._role_d = dict()
        for key, value in d.items():
            if key == 'parents':
                self._parents = value
            elif key == 'attributes':
                self._attributes = value
            elif key == 'permissions':
                self._permissions = value
            else:
                self._role_d[key] = value

    def deserialize(self):
        ou_d = self._role_d['ou']
        has_ou = bool(ou_d)
        ou = None if not has_ou else search_ou(ou_d)
        if has_ou and not ou:
            raise DataImportError(
                    "Can't import role because missing Organizational Unit : "
                    "%s" % ou_d)

        kwargs = self._role_d.copy()
        del kwargs['ou']
        del kwargs['service']
        if has_ou:
            kwargs['ou'] = ou

        obj = search_role(self._role_d)
        if obj:  # Role already exist
            self._obj = obj
            status = 'updated'
            update_model(self._obj, kwargs)
        else:  # Create role
            self._obj = get_role_model().objects.create(**kwargs)
            status = 'created'

        # Ensure admin role is created.
        # Absoluteley necessary to create
        # parentings relationship later on,
        # since we don't deserialize technical role.
        self._obj.get_admin_role()
        return self._obj, status

    def attributes(self):
        """ Update attributes (delete everything then create)
        """
        created, deleted = [], []
        for attr in self._obj.attributes.all():
            attr.delete()
            deleted.append(attr)
        # Create attributes
        if self._attributes:
            for attr_dict in self._attributes:
                attr_dict['role'] = self._obj
                created.append(RoleAttribute.objects.create(**attr_dict))

        return created, deleted

    def parentings(self):
        """ Update parentings (delete everything then create)
        """
        created, deleted = [], []
        Parenting = get_role_parenting_model()
        for parenting in Parenting.objects.filter(child=self._obj, direct=True):
            parenting.delete()
            deleted.append(parenting)

        if self._parents:
            for parent_d in self._parents:
                parent = search_role(parent_d)
                if not parent:
                    raise DataImportError("Could not find role : %s" % parent_d)
                created.append(Parenting.objects.create(
                    child=self._obj, direct=True, parent=parent))

        return created, deleted

    def permissions(self):
        """ Update permissions (delete everything then create)
        """
        created, deleted = [], []
        for perm in self._obj.permissions.all():
            perm.delete()
            deleted.append(perm)
        self._obj.permissions.clear()
        if self._permissions:
            for perm in self._permissions:
                op = Operation.objects.get_by_natural_key_json(perm['operation'])
                ou = get_ou_model().objects.get_by_natural_key_json(
                    perm['ou']) if perm['ou'] else None
                ct = ContentType.objects.get_by_natural_key_json(perm['target_ct'])
                target = ct.model_class().objects.get_by_natural_key_json(perm['target'])
                perm = get_permission_model().objects.create(
                    operation=op, ou=ou, target_ct=ct, target_id=target.pk)
                self._obj.permissions.add(perm)
                created.append(perm)

        return created, deleted


class ImportResult(object):

    def __init__(self):
        self.roles = {'created': [], 'updated': []}
        self.ous = {'created': [], 'updated': []}
        self.attributes = {'created': [], 'deleted': []}
        self.parentings = {'created': [], 'deleted': []}
        self.permissions = {'created': [], 'deleted': []}

    def update_roles(self, role, d_status):
        self.roles[d_status].append(role)

    def update_ous(self, ou, status):
        self.ous[status].append(ou)

    def _bulk_update(self, attrname, created, deleted):
        attr = getattr(self, attrname)
        attr['created'].extend(created)
        attr['deleted'].extend(deleted)

    def update_attributes(self, created, deleted):
        self._bulk_update('attributes', created, deleted)

    def update_parentings(self, created, deleted):
        self._bulk_update('parentings', created, deleted)

    def update_permissions(self, created, deleted):
        self._bulk_update('permissions', created, deleted)

    def to_str(self, verbose=False):
        res = ""
        for attr in ('roles', 'ous', 'parentings', 'permissions', 'attributes'):
            data = getattr(self, attr)
            for status in ('created', 'updated', 'deleted'):
                if status in data:
                    s_data = data[status]
                    res += "%s %s %s\n" % (len(s_data), attr, status)
        return res


def import_ou(ou_d):
    OU = get_ou_model()
    # ou = search_ou([ou_d['slug']])
    ou = search_ou(ou_d)
    if ou is None:
        ou = OU.objects.create(**ou_d)
        status = 'created'
    else:
        update_model(ou, ou_d)
        status = 'updated'
    # Ensure admin role is created
    ou.get_admin_role()
    return ou, status


def import_site(json_d, import_context):
    result = ImportResult()

    for ou_d in json_d.get('ous', []):
        result.update_ous(*import_ou(ou_d))

    roles_ds = [RoleDeserializer(role_d, import_context) for role_d in json_d.get('roles', [])
                if not role_d['slug'].startswith('_')]

    for ds in roles_ds:
        result.update_roles(*ds.deserialize())

    if import_context.role_attributes_update:
        for ds in roles_ds:
            result.update_attributes(*ds.attributes())

    if import_context.role_parentings_update:
        for ds in roles_ds:
            result.update_parentings(*ds.parentings())

    if import_context.role_permissions_update:
        for ds in roles_ds:
            result.update_permissions(*ds.permissions())

    if import_context.ou_delete_orphans:
        raise DataImportError(
            "Unsupported context value for ou_delete_orphans : %s" % (
                import_context.ou_delete_orphans))

    if import_context.role_delete_orphans:
        # FIXME : delete each role that is in DB but not in the export
        raise DataImportError(
            "Unsupported context value for role_delete_orphans : %s" % (
                import_context.role_delete_orphans))

    return result
