import uuid
import collections

from django.db import models
from django.utils.translation import ugettext_lazy as _, ugettext
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.html import format_html
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.core.urlresolvers import reverse
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import HttpResponseRedirect, QueryDict
from django.views.generic.detail import SingleObjectMixin
from django.views.generic import View

from import_export.fields import Field

from authentic2.constants import SWITCH_USER_SESSION_KEY
from authentic2.models import Attribute, PasswordReset
from authentic2.utils import switch_user, send_password_reset_mail, redirect, send_email_change_email
from authentic2.a2_rbac.utils import get_default_ou
from authentic2 import hooks
from django_rbac.utils import get_role_model, get_role_parenting_model, get_ou_model


from .views import BaseTableView, BaseAddView, \
    BaseEditView, ActionMixin, OtherActionsMixin, Action, ExportMixin, \
    BaseSubTableView, HideOUColumnMixin, BaseDeleteView, BaseDetailView
from .tables import UserTable, UserRolesTable, OuUserRolesTable
from .forms import (UserSearchForm, UserAddForm, UserEditForm,
    UserChangePasswordForm, ChooseUserRoleForm, UserRoleSearchForm, UserChangeEmailForm)
from .resources import UserResource
from .utils import get_ou_count
from . import app_settings


class UsersView(HideOUColumnMixin, BaseTableView):
    template_name = 'authentic2/manager/users.html'
    model = get_user_model()
    table_class = UserTable
    permissions = ['custom_user.search_user']
    search_form_class = UserSearchForm
    title = _('Users')

    def is_ou_specified(self):
        return self.search_form.is_valid() \
            and self.search_form.cleaned_data.get('ou')

    def get_queryset(self):
        qs = super(UsersView, self).get_queryset()
        qs = qs.select_related('ou')
        qs = qs.prefetch_related('roles', 'roles__parent_relation__parent')
        return qs

    def get_search_form_kwargs(self):
        kwargs = super(UsersView, self).get_search_form_kwargs()
        kwargs['minimum_chars'] = app_settings.USER_SEARCH_MINIMUM_CHARS
        kwargs['show_all_ou'] = app_settings.SHOW_ALL_OU
        return kwargs

    def filter_by_search(self, qs):
        qs = super(UsersView, self).filter_by_search(qs)
        if not self.search_form.is_valid():
            qs = qs.filter(ou=self.request.user.ou)
        return qs

    def get_table(self, **kwargs):
        table = super(UsersView, self).get_table(**kwargs)
        if self.search_form.not_enough_chars():
            user_qs = self.search_form.filter_by_ou(self.get_queryset())
            table.empty_text = _('Enter at least %(limit)d characters '
                                 '(%(user_count)d users)') % {
                'limit': self.search_form.minimum_chars,
                'user_count': user_qs.count(),
            }
        return table

    def get_context_data(self, **kwargs):
        ctx = super(UsersView, self).get_context_data()
        if get_ou_count() < 2:
            ou = get_default_ou()
        else:
            ou = self.search_form.cleaned_data.get('ou')
        if ou and self.request.user.has_ou_perm('custom_user.add_user', ou):
            ctx['add_ou'] = ou
        return ctx


users = UsersView.as_view()


class UserAddView(BaseAddView):
    model = get_user_model()
    title = _('Create user')
    action = _('Create')
    fields = [
        'username',
        'first_name',
        'last_name',
        'email',
        'generate_password',
        'password1',
        'password2',
        'reset_password_at_next_login',
        'send_mail']
    form_class = UserAddForm
    permissions = ['custom_user.add_user']
    template_name = 'authentic2/manager/user_add.html'

    def get_form_kwargs(self):
        kwargs = super(UserAddView, self).get_form_kwargs()
        qs = self.request.user.ous_with_perm('custom_user.add_user')
        self.ou = qs.get(pk=self.kwargs['ou_pk'])
        kwargs['ou'] = self.ou
        return kwargs

    def get_fields(self):
        fields = list(self.fields)
        i = fields.index('generate_password')
        if self.request.user.is_superuser and \
                'is_superuser' not in self.fields:
            fields.insert(i, 'is_superuser')
            i += 1
        for attribute in Attribute.objects.all():
            fields.insert(i, attribute.name)
            i += 1
        return fields

    def get_success_url(self):
        return reverse('a2-manager-user-detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super(UserAddView, self).get_context_data(**kwargs)
        context['cancel_url'] = '../..'
        context['ou'] = self.ou
        return context

    def form_valid(self, form):
        response = super(UserAddView, self).form_valid(form)
        hooks.call_hooks('event', name='manager-add-user', user=self.request.user,
                         instance=form.instance, form=form)
        return response

user_add = UserAddView.as_view()


class UserDetailView(OtherActionsMixin, BaseDetailView):
    model = get_user_model()
    fields = ['username', 'ou', 'first_name', 'last_name', 'email']
    form_class = UserEditForm
    template_name = 'authentic2/manager/user_detail.html'
    slug_field = 'uuid'

    @property
    def title(self):
        return self.object.get_full_name()

    def get_other_actions(self):
        for action in super(UserDetailView, self).get_other_actions():
            yield action
        yield Action('password_reset', _('Reset password'),
                     permission='custom_user.reset_password_user')
        if self.object.is_active:
            yield Action('deactivate', _('Suspend'),
                         permission='custom_user.activate_user')
        else:
            yield Action('activate', _('Activate'),
                         permission='custom_user.activate_user')
        if PasswordReset.objects.filter(user=self.object).exists():
            yield Action('delete_password_reset', _('Do not force password change on next login'),
                         permission='custom_user.reset_password_user')
        else:
            yield Action('force_password_change', _('Force password change on '
                         'next login'),
                         permission='custom_user.reset_password_user')
        yield Action('change_password', _('Change user password'),
                     url_name='a2-manager-user-change-password',
                     permission='custom_user.change_password_user')
        if self.request.user.is_superuser:
            yield Action('switch_user', _('Impersonate this user'))
        if self.object.ou and self.object.ou.validate_emails:
            yield Action('change_email', _('Change user email'),
                         url_name='a2-manager-user-change-email',
                         permission='custom_user.change_email_user')

    def action_force_password_change(self, request, *args, **kwargs):
        PasswordReset.objects.get_or_create(user=self.object)

    def action_activate(self, request, *args, **kwargs):
        self.object.is_active = True
        self.object.save()

    def action_deactivate(self, request, *args, **kwargs):
        if request.user == self.object:
            messages.warning(request, _('You cannot desactivate your own '
                             'user'))
        else:
            self.object.is_active = False
            self.object.save()

    def action_password_reset(self, request, *args, **kwargs):
        user = self.object
        if not user.email:
            messages.info(request, _('User has no email, it\'not possible to '
                                     'send him am email to reset its '
                                     'password'))
            return
        send_password_reset_mail(user, request=request)
        messages.info(request, _('A mail was sent to %s') % self.object.email)

    def action_delete_password_reset(self, request, *args, **kwargs):
        PasswordReset.objects.filter(user=self.object).delete()

    def action_switch_user(self, request, *args, **kwargs):
        return switch_user(request, self.object)

    # Copied from PasswordResetForm implementation
    def send_mail(self, subject_template_name, email_template_name,
                  context, to_email):
        """
        Sends a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(subject, body, to=[to_email])
        email_message.send()

    def get_fields(self):
        fields = list(self.fields)
        for attribute in Attribute.objects.all():
            fields.append(attribute.name)
        if self.request.user.is_superuser and \
                'is_superuser' not in self.fields:
            fields.append('is_superuser')
        return fields

    def get_form(self, *args, **kwargs):
        form = super(UserDetailView, self).get_form(*args, **kwargs)
        if 'email' in form.fields:
            if self.object.email_verified:
                comment = _('Email verified')
            else:
                comment = _('Email not verified')
            form.fields['email'].help_text = format_html('<b>{0}</b>', comment)
        return form

    @classmethod
    def has_perm_on_roles(self, user, instance):
        role_qs = get_role_model().objects.all()
        if app_settings.ROLE_MEMBERS_FROM_OU and instance.ou:
            role_qs = role_qs.filter(ou=instance.ou)
        return user.filter_by_perm('a2_rbac.change_role', role_qs).exists()

    def get_context_data(self, **kwargs):
        kwargs['default_ou'] = get_default_ou
        roles = self.object.roles_and_parents().order_by('ou__name', 'name')
        roles_by_ou = collections.OrderedDict()
        for role in roles:
            roles_by_ou.setdefault(role.ou.name if role.ou else '', []).append(role)
        kwargs['roles'] = roles
        kwargs['roles_by_ou'] = roles_by_ou
        # show modify roles button only if something is possible
        kwargs['can_change_roles'] = self.has_perm_on_roles(self.request.user, self.object)
        user_data = []
        user_data += [data for datas in hooks.call_hooks('manager_user_data', self, self.object)
                      for data in datas]
        kwargs['user_data'] = user_data
        ctx = super(UserDetailView, self).get_context_data(**kwargs)
        return ctx

user_detail = UserDetailView.as_view()


class UserEditView(OtherActionsMixin, ActionMixin, BaseEditView):
    model = get_user_model()
    template_name = 'authentic2/manager/user_edit.html'
    form_class = UserEditForm
    permissions = ['custom_user.change_user']
    fields = ['username', 'ou', 'first_name', 'last_name']
    success_url = '..'
    slug_field = 'uuid'
    action = _('Change')
    title = _('Edit user')

    def get_fields(self):
        fields = list(self.fields)
        if not self.object.ou or not self.object.ou.validate_emails:
            fields.append('email')
        for attribute in Attribute.objects.all():
            fields.append(attribute.name)
        if self.request.user.is_superuser and \
                'is_superuser' not in self.fields:
            fields.append('is_superuser')
        return fields

    def form_valid(self, form):
        response = super(UserEditView, self).form_valid(form)
        hooks.call_hooks('event', name='manager-edit-user', user=self.request.user,
                         instance=form.instance, form=form)
        return response

user_edit = UserEditView.as_view()


class UsersExportView(ExportMixin, UsersView):
    permissions = ['custom_user.view_user']
    resource_class = UserResource
    export_prefix = 'users-'

    def get_resource(self):
        '''Subclass default UserResource class to dynamically add field for extra attributes'''
        attrs = collections.OrderedDict()
        for attribute in Attribute.objects.all():
            attrs['attribute_%s' % attribute.name] = Field(attribute='attributes__%s' % attribute.name)
        custom_class = type('UserResourceClass', (self.resource_class,), attrs)
        return custom_class()

    def get_queryset(self):
        '''Prefetch attribute values.'''
        qs = super(UsersExportView, self).get_queryset()
        return qs.prefetch_related('attribute_values', 'attribute_values__attribute')

users_export = UsersExportView.as_view()


class UserChangePasswordView(BaseEditView):
    template_name = 'authentic2/manager/form.html'
    model = get_user_model()
    form_class = UserChangePasswordForm
    permissions = ['custom_user.change_password_user']
    title = _('Change user password')
    success_url = '..'
    slug_field = 'uuid'

    def get_success_message(self, cleaned_data):
        if cleaned_data.get('send_mail'):
            return ugettext('New password sent to %s') % self.object.email
        else:
            return ugettext('New password set')

    def form_valid(self, form):
        response = super(UserChangePasswordView, self).form_valid(form)
        hooks.call_hooks('event', name='manager-change-password', user=self.request.user,
                         instance=form.instance, form=form)
        return response


user_change_password = UserChangePasswordView.as_view()


class UserChangeEmailView(BaseEditView):
    template_name = 'authentic2/manager/user_change_email.html'
    model = get_user_model()
    form_class = UserChangeEmailForm
    permissions = ['custom_user.change_email_user']
    success_url = '..'
    slug_field = 'uuid'
    title = _('Change user email')

    def get_success_message(self, cleaned_data):
        if cleaned_data['new_email'] != self.object.email:
            return ugettext('A mail was sent to %s to verify it.') % cleaned_data['new_email']
        return None

    def form_valid(self, form):
        response = super(UserChangeEmailView, self).form_valid(form)
        new_email = form.cleaned_data['new_email']
        hooks.call_hooks(
                'event',
                name='manager-change-email-request',
                user=self.request.user,
                instance=form.instance,
                form=form,
                email=new_email)
        return response

user_change_email = UserChangeEmailView.as_view()


class UserRolesView(HideOUColumnMixin, BaseSubTableView):
    model = get_user_model()
    form_class = ChooseUserRoleForm
    search_form_class = UserRoleSearchForm
    success_url = '.'
    slug_field = 'uuid'

    @property
    def template_name(self):
        if self.is_ou_specified():
            return 'authentic2/manager/user_ou_roles.html'
        else:
            return 'authentic2/manager/user_roles.html'

    @property
    def table_pagination(self):
        if self.is_ou_specified():
            return False
        return None

    @property
    def table_class(self):
        if self.is_ou_specified():
            return OuUserRolesTable
        else:
            return UserRolesTable

    def is_ou_specified(self):
        '''Differentiate view of all user's roles from view of roles by OU'''
        return (self.search_form.is_valid()
                and self.search_form.cleaned_data.get('ou_filter') != 'all')

    def get_table_queryset(self):
        if self.is_ou_specified():
            roles = self.object.roles.all()
            User = get_user_model()
            Role = get_role_model()
            RoleParenting = get_role_parenting_model()
            rp_qs = RoleParenting.objects.filter(child__in=roles)
            qs = Role.objects.all()
            qs = qs.prefetch_related(models.Prefetch(
                'child_relation', queryset=rp_qs, to_attr='via'))
            qs = qs.prefetch_related(models.Prefetch(
                'members', queryset=User.objects.filter(pk=self.object.pk),
                to_attr='member'))
            qs2 = self.request.user.filter_by_perm('a2_rbac.change_role', qs)
            managable_ids = map(str, qs2.values_list('pk', flat=True))
            qs = qs.extra(select={'has_perm': 'a2_rbac_role.id in (%s)' % ', '.join(managable_ids)})
            qs = qs.exclude(slug__startswith='_a2-managers-of-role')
            return qs
        else:
            return self.object.roles_and_parents()

    def get_table_data(self):
        qs = super(UserRolesView, self).get_table_data()
        if self.is_ou_specified():
            qs = list(qs)
        return qs

    def authorize(self, request, *args, **kwargs):
        response = super(UserRolesView, self).authorize(request, *args, **kwargs)
        if response is not None:
            return response
        if not UserDetailView.has_perm_on_roles(request.user, self.object):
            return redirect(request, 'a2-manager-user-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        user = self.object
        role = form.cleaned_data['role']
        action = form.cleaned_data['action']
        if self.request.user.has_perm('a2_rbac.change_role', role):
            if action == 'add':
                if user.roles.filter(pk=role.pk):
                    messages.warning(
                        self.request,
                        _('User {user} has already the role {role}.')
                        .format(user=user, role=role))
                else:
                    user.roles.add(role)
                    hooks.call_hooks('event', name='manager-add-role-member',
                                     user=self.request.user, role=role, member=user)
            elif action == 'remove':
                user.roles.remove(role)
                hooks.call_hooks('event', name='manager-remove-role-member', user=self.request.user,
                                 role=role, member=user)
        else:
            messages.warning(self.request, _('You are not authorized'))
        return super(UserRolesView, self).form_valid(form)

    def get_search_form_kwargs(self):
        kwargs = super(UserRolesView, self).get_search_form_kwargs()
        kwargs['all_ou_label'] = u''
        kwargs['user'] = self.object
        kwargs['role_members_from_ou'] = app_settings.ROLE_MEMBERS_FROM_OU
        kwargs['show_all_ou'] = app_settings.SHOW_ALL_OU
        kwargs['queryset'] = self.request.user.filter_by_perm('a2_rbac.view_role', get_role_model().objects.all())
        if self.object.ou_id:
            initial = kwargs.setdefault('initial', {})
            initial['ou'] = str(self.object.ou_id)
        return kwargs

    def get_form_kwargs(self):
        kwargs = super(UserRolesView, self).get_form_kwargs()
        # if role members can only be from the same OU, we filter roles based on the user's ou
        if app_settings.ROLE_MEMBERS_FROM_OU and self.object.ou_id:
            kwargs['ou'] = self.object.ou
        return kwargs


roles = UserRolesView.as_view()


class UserDeleteView(BaseDeleteView):
    model = get_user_model()
    title = _('Delete user')
    template_name = 'authentic2/manager/user_delete.html'

    def get_success_url(self):
        return reverse('a2-manager-users')

    def delete(self, request, *args, **kwargs):
        response = super(UserDeleteView, self).delete(request, *args, **kwargs)
        hooks.call_hooks('event', name='manager-delete-user', user=request.user,
                         instance=self.object)
        return response


user_delete = UserDeleteView.as_view()
