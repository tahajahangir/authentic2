from django.core.exceptions import PermissionDenied
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView, FormView, TemplateView
from django.views.generic.edit import FormMixin, DeleteView
from django.views.generic.detail import SingleObjectMixin
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.db.models.query import Q
from django.db.models import Count
from django.core.urlresolvers import reverse
from django.http import Http404
from django.contrib.auth import get_user_model

from django_rbac.utils import get_role_model, get_permission_model, \
    get_role_parenting_model, get_ou_model

from authentic2.utils import redirect
from authentic2 import hooks

from . import tables, views, resources, forms, app_settings


class RolesMixin(object):
    service_roles = True
    admin_roles = False

    def get_queryset(self):
        qs = super(RolesMixin, self).get_queryset()
        qs = qs.select_related('ou')
        Permission = get_permission_model()
        permission_ct = ContentType.objects.get_for_model(Permission)
        ct_ct = ContentType.objects.get_for_model(ContentType)
        ou_ct = ContentType.objects.get_for_model(get_ou_model())
        permission_qs = Permission.objects.filter(target_ct_id__in=[ct_ct.id, ou_ct.id]) \
            .values_list('id', flat=True)
        # only non role-admin roles, they are accessed through the
        # RoleManager views
        if not self.admin_roles:
            qs = qs.filter(Q(admin_scope_ct__isnull=True) |
                           Q(admin_scope_ct=permission_ct,
                             admin_scope_id__in=permission_qs))
        if not self.service_roles:
            qs = qs.filter(service__isnull=True)
        return qs


class RolesView(views.HideOUColumnMixin, RolesMixin, views.BaseTableView):
    template_name = 'authentic2/manager/roles.html'
    model = get_role_model()
    table_class = tables.RoleTable
    search_form_class = forms.RoleSearchForm
    permissions = ['a2_rbac.search_role']
    title = _('Roles')

    def get_queryset(self):
        qs = super(RolesView, self).get_queryset()
        qs = qs.annotate(member_count=Count('members'))
        return qs

    def get_search_form_kwargs(self):
        kwargs = super(RolesView, self).get_search_form_kwargs()
        kwargs['queryset'] = self.get_queryset()
        return kwargs

    def authorize(self, request, *args, **kwargs):
        super(RolesView, self).authorize(request, *args, **kwargs)
        self.can_add = bool(request.user.ous_with_perm('a2_rbac.add_role'))


listing = RolesView.as_view()


class RoleAddView(views.BaseAddView):
    template_name = 'authentic2/manager/role_add.html'
    model = get_role_model()
    title = _('Add role')
    success_view_name = 'a2-manager-role-members'

    def get_form_class(self):
        return forms.get_role_form_class()

    def form_valid(self, form):
        response = super(RoleAddView, self).form_valid(form)
        hooks.call_hooks('event', name='manager-add-role', user=self.request.user,
                         instance=form.instance, form=form)
        return response


add = RoleAddView.as_view()


class RolesExportView(views.ExportMixin, RolesView):
    resource_class = resources.RoleResource

export = RolesExportView.as_view()


class RoleViewMixin(RolesMixin):
    model = get_role_model()


class RoleEditView(RoleViewMixin, views.BaseEditView):
    template_name = 'authentic2/manager/role_edit.html'
    title = _('Edit role description')

    def get_form_class(self):
        return forms.get_role_form_class()

    def form_valid(self, form):
        response = super(RoleEditView, self).form_valid(form)
        hooks.call_hooks('event', name='manager-edit-role', user=self.request.user,
                         instance=form.instance, form=form)
        return response

edit = RoleEditView.as_view()


class RoleMembersView(views.HideOUColumnMixin, RoleViewMixin, views.BaseSubTableView):
    template_name = 'authentic2/manager/role_members.html'
    table_class = tables.RoleMembersTable
    form_class = forms.ChooseUserForm
    success_url = '.'
    search_form_class = forms.UserSearchForm
    permissions = ['a2_rbac.view_role']

    @property
    def title(self):
        return self.get_instance_name()

    def get_table_queryset(self):
        return self.object.all_members()

    def form_valid(self, form):
        user = form.cleaned_data['user']
        action = form.cleaned_data['action']
        if self.can_change:
            if action == 'add':
                if self.object.members.filter(pk=user.pk).exists():
                    messages.warning(self.request, _('User already in this role.'))
                else:
                    self.object.members.add(user)
                    hooks.call_hooks('event', name='manager-add-role-member',
                                     user=self.request.user, role=self.object, member=user)
            elif action == 'remove':
                if not self.object.members.filter(pk=user.pk).exists():
                    messages.warning(self.request, _('User was not in this role.'))
                else:
                    self.object.members.remove(user)
                    hooks.call_hooks('event', name='manager-remove-role-member',
                                     user=self.request.user, role=self.object, member=user)
        else:
            messages.warning(self.request, _('You are not authorized'))
        return super(RoleMembersView, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super(RoleMembersView, self).get_form_kwargs()
        # if role's members can only be from the same OU we filter user based on the role's OU
        if app_settings.ROLE_MEMBERS_FROM_OU:
            kwargs['ou'] = self.object.ou
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super(RoleMembersView, self).get_context_data(**kwargs)
        ctx['children'] = views.filter_view(self.request,
                                            self.object.children(include_self=False,
                                            annotate=True))
        ctx['parents'] = views.filter_view(self.request,
                                           self.object.parents(include_self=False,
                                           annotate=True))
        ctx['admin_roles'] = views.filter_view(self.request,
                                               self.object.get_admin_role().children(
                                                   include_self=False, annotate=True))
        return ctx

members = RoleMembersView.as_view()


class RoleChildrenView(views.HideOUColumnMixin, RoleViewMixin, views.BaseSubTableView):
    template_name = 'authentic2/manager/role_children.html'
    table_class = tables.RoleChildrenTable
    form_class = forms.ChooseRoleForm
    search_form_class = forms.RoleSearchForm
    success_url = '.'
    permissions = ['a2_rbac.view_role']

    def get_table_queryset(self):
        return self.object.children(include_self=False, annotate=True)

    def form_valid(self, form):
        RoleParenting = get_role_parenting_model()
        role = form.cleaned_data['role']
        action = form.cleaned_data['action']
        if self.can_change:
            if action == 'add':
                if RoleParenting.objects.filter(parent=self.object, child=role,
                                                direct=True).exists():
                    messages.warning(self.request, _('Role "%s" is already a '
                                     'child of this role.') % role.name)
                else:
                    self.object.add_child(role)
                    hooks.call_hooks('event', name='manager-add-child-role',
                                     user=self.request.user, parent=self.object, child=role)
            elif action == 'remove':
                hooks.call_hooks('event', name='manager-remove-child-role',
                                 user=self.request.user, parent=self.object, child=role)
                self.object.remove_child(role)
        else:
            messages.warning(self.request, _('You are not authorized'))
        return super(RoleChildrenView, self).form_valid(form)

children = RoleChildrenView.as_view()


class RoleDeleteView(RoleViewMixin, views.BaseDeleteView):
    title = _('Delete role')
    template_name = 'authentic2/manager/role_delete.html'

    def post(self, request, *args, **kwargs):
        if not self.can_delete:
            raise PermissionDenied
        return super(RoleDeleteView, self).post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('a2-manager-roles')

    def form_valid(self, form):
        response = super(RoleDeleteView, self).form_valid(form)
        hooks.call_hooks('event', name='manager-delete-role', user=self.request.user,
                         role=form.instance)
        return response

delete = RoleDeleteView.as_view()


class RolePermissionsView(RoleViewMixin, views.BaseSubTableView):
    template_name = 'authentic2/manager/role_permissions.html'
    table_class = tables.PermissionTable
    form_class = forms.ChoosePermissionForm
    success_url = '.'
    permissions = ['a2_rbac.admin_permission']
    title = _('Permissions')

    def get_table_queryset(self):
        return self.object.permissions.all()

    def form_valid(self, form):
        if self.can_change:
            operation = form.cleaned_data.get('operation')
            ou = form.cleaned_data.get('ou')
            target = form.cleaned_data.get('target')
            action = form.cleaned_data.get('action')
            Permission = get_permission_model()
            if action == 'add' and operation and target:
                perm, created = Permission.objects \
                    .get_or_create(operation=operation, ou=ou,
                                   target_ct=ContentType.objects.get_for_model(
                                       target),
                                   target_id=target.pk)
                self.object.permissions.add(perm)
                hooks.call_hooks('event', name='manager-add-permission', user=self.request.user,
                                 role=self.object, permission=perm)
            elif action == 'remove':
                try:
                    permission_id = int(self.request.POST.get('permission', ''))
                    perm = Permission.objects.get(id=permission_id)
                except (ValueError, Permission.DoesNotExist):
                    pass
                else:
                    if self.object.permissions.filter(id=permission_id).exists():
                        self.object.permissions.remove(perm)
                        hooks.call_hooks('event', name='manager-remove-permission',
                                         user=self.request.user, role=self.object, permission=perm)
        else:
            messages.warning(self.request, _('You are not authorized'))
        return super(RolePermissionsView, self).form_valid(form)

permissions = RolePermissionsView.as_view()


class RoleMembersExportView(views.ExportMixin, RoleMembersView):
    resource_class = resources.UserResource
    permissions = ['a2_rbac.view_role']

    def get_data(self):
        return self.get_table_data()

members_export = RoleMembersExportView.as_view()


class RoleAddChildView(views.AjaxFormViewMixin, views.TitleMixin,
                       views.PermissionMixin, SingleObjectMixin, FormView):
    title = _('Add child role')
    model = get_role_model()
    form_class = forms.RolesForm
    success_url = '..'
    template_name = 'authentic2/manager/form.html'
    permissions = ['a2_rbac.change_role']

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(RoleAddChildView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        parent = self.get_object()
        for role in form.cleaned_data['roles']:
            parent.add_child(role)
            hooks.call_hooks('event', name='manager-add-child-role', user=self.request.user,
                             parent=parent, child=role)
        return super(RoleAddChildView, self).form_valid(form)

add_child = RoleAddChildView.as_view()


class RoleAddParentView(views.AjaxFormViewMixin, views.TitleMixin,
                        SingleObjectMixin, FormView):
    title = _('Add parent role')
    model = get_role_model()
    form_class = forms.RolesForChangeForm
    success_url = '..'
    template_name = 'authentic2/manager/form.html'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_internal():
            raise PermissionDenied
        return super(RoleAddParentView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        child = self.get_object()
        for role in form.cleaned_data['roles']:
            child.add_parent(role)
            hooks.call_hooks('event', name='manager-add-child-role', user=self.request.user,
                             parent=role, child=child)
        return super(RoleAddParentView, self).form_valid(form)

add_parent = RoleAddParentView.as_view()


class RoleRemoveChildView(views.AjaxFormViewMixin, SingleObjectMixin,
                          views.PermissionMixin, TemplateView):
    title = _('Remove child role')
    model = get_role_model()
    success_url = '../..'
    template_name = 'authentic2/manager/role_remove_child.html'
    permissions = ['a2_rbac.change_role']

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.child = self.get_queryset().get(pk=kwargs['child_pk'])
        return super(RoleRemoveChildView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(RoleRemoveChildView, self).get_context_data(**kwargs)
        ctx['child'] = self.child
        return ctx

    def post(self, request, *args, **kwargs):
        self.object.remove_child(self.child)
        hooks.call_hooks('event', name='manager-remove-child-role', user=self.request.user,
                         parent=self.object, child=self.child)
        return redirect(self.request, self.success_url)

remove_child = RoleRemoveChildView.as_view()


class RoleRemoveParentView(views.AjaxFormViewMixin, SingleObjectMixin,
                           TemplateView):
    title = _('Remove parent role')
    model = get_role_model()
    success_url = '../..'
    template_name = 'authentic2/manager/role_remove_parent.html'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_internal():
            raise PermissionDenied
        self.parent = self.get_queryset().get(pk=kwargs['parent_pk'])
        return super(RoleRemoveParentView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(RoleRemoveParentView, self).get_context_data(**kwargs)
        ctx['parent'] = self.parent
        return ctx

    def post(self, request, *args, **kwargs):
        if not self.request.user.has_perm('a2_rbac.change_role', self.parent):
            raise PermissionDenied
        self.object.remove_parent(self.parent)
        hooks.call_hooks('event', name='manager-remove-child-role', user=self.request.user,
                         parent=self.parent, child=self.object)
        return redirect(self.request, self.success_url)

remove_parent = RoleRemoveParentView.as_view()


class RoleAddAdminRoleView(views.AjaxFormViewMixin, views.TitleMixin,
                       views.PermissionMixin, SingleObjectMixin, FormView):
    title = _('Add admin role')
    model = get_role_model()
    form_class = forms.RolesForm
    success_url = '..'
    template_name = 'authentic2/manager/form.html'
    permissions = ['a2_rbac.change_role']

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(RoleAddAdminRoleView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        administered_role = self.get_object()
        for role in form.cleaned_data['roles']:
            administered_role.get_admin_role().add_child(role)
            hooks.call_hooks('event', name='manager-add-admin-role', user=self.request.user,
                             role=administered_role, admin_role=role)
        return super(RoleAddAdminRoleView, self).form_valid(form)

add_admin_role = RoleAddAdminRoleView.as_view()


class RoleRemoveAdminRoleView(views.TitleMixin, views.AjaxFormViewMixin, SingleObjectMixin,
                          views.PermissionMixin, TemplateView):
    title = _('Remove admin role')
    model = get_role_model()
    success_url = '../..'
    template_name = 'authentic2/manager/role_remove_admin_role.html'
    permissions = ['a2_rbac.change_role']

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.child = self.get_queryset().get(pk=kwargs['role_pk'])
        return super(RoleRemoveAdminRoleView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(RoleRemoveAdminRoleView, self).get_context_data(**kwargs)
        ctx['child'] = self.child
        return ctx

    def post(self, request, *args, **kwargs):
        self.object.get_admin_role().remove_child(self.child)
        hooks.call_hooks('event', name='manager-remove-admin-role',
                         user=self.request.user, role=self.object, admin_role=self.child)
        return redirect(self.request, self.success_url)

remove_admin_role = RoleRemoveAdminRoleView.as_view()


class RoleAddAdminUserView(views.AjaxFormViewMixin, views.TitleMixin,
                       views.PermissionMixin, SingleObjectMixin, FormView):
    title = _('Add admin user')
    model = get_role_model()
    form_class = forms.UsersForm
    success_url = '..'
    template_name = 'authentic2/manager/form.html'
    permissions = ['a2_rbac.change_role']

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(RoleAddAdminUserView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        administered_role = self.get_object()
        for user in form.cleaned_data['users']:
            administered_role.get_admin_role().members.add(user)
            hooks.call_hooks('event', name='manager-add-admin-role-user', user=self.request.user,
                             role=administered_role, admin=user)
        return super(RoleAddAdminUserView, self).form_valid(form)

add_admin_user = RoleAddAdminUserView.as_view()


class RoleRemoveAdminUserView(views.TitleMixin, views.AjaxFormViewMixin, SingleObjectMixin,
                          views.PermissionMixin, TemplateView):
    title = _('Remove admin user')
    model = get_role_model()
    success_url = '../..'
    template_name = 'authentic2/manager/role_remove_admin_user.html'
    permissions = ['a2_rbac.change_role']

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.user = get_user_model().objects.get(pk=kwargs['user_pk'])
        return super(RoleRemoveAdminUserView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(RoleRemoveAdminUserView, self).get_context_data(**kwargs)
        ctx['user'] = self.user
        return ctx

    def post(self, request, *args, **kwargs):
        self.object.get_admin_role().members.remove(self.user)
        hooks.call_hooks('event', name='remove-remove-admin-role-user', user=self.request.user,
                         role=self.object, admin=self.user)
        return redirect(self.request, self.success_url)

remove_admin_user = RoleRemoveAdminUserView.as_view()
