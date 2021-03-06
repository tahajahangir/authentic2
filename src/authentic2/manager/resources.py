from import_export.resources import ModelResource
from import_export.fields import Field
from import_export.widgets import Widget

from authentic2.compat import get_user_model
from authentic2.a2_rbac.models import Role


class ListWidget(Widget):
    def clean(self, value):
        raise NotImplementedError

    def render(self, value):
        return u', '.join(map(unicode, value.all()))


class UserResource(ModelResource):
    roles = Field()

    def dehydrate_roles(self, instance):
        result = set()
        for role in instance.roles.all():
            result.add(role)
            for pr in role.parent_relation.all():
                result.add(pr.parent)
        return ', '.join(map(unicode, result))

    class Meta:
        model = get_user_model()
        exclude = ('password', 'user_permissions', 'is_staff',
                   'is_superuser', 'groups')
        export_order = ('ou', 'uuid', 'id', 'username', 'email',
                        'first_name', 'last_name', 'last_login',
                        'date_joined', 'roles')
        widgets = {
            'roles': {
                'field': 'name',
            },
            'ou': {
                'field': 'name',
            }
        }


class RoleResource(ModelResource):
    members = Field(attribute='members', widget=ListWidget())

    class Meta:
        model = Role
        fields = ('name', 'slug', 'members')
        export_order = fields
