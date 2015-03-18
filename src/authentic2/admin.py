from copy import deepcopy
import pprint

from django.contrib import admin
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.utils.http import urlencode
from django.http import HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.admin.utils import flatten_fieldsets

from .nonce.models import Nonce
from . import forms, models, admin_forms, compat, app_settings

def cleanup_action(modeladmin, request, queryset):
    queryset.cleanup()
cleanup_action.short_description = _('Cleanup expired objects')

class CleanupAdminMixin(admin.ModelAdmin):
    def get_actions(self, request):
        actions = super(CleanupAdminMixin, self).get_actions(request)
        if hasattr(self.model.objects.none(), 'cleanup'):
            actions['cleanup_action'] = cleanup_action, 'cleanup_action', cleanup_action.short_description
        return actions

class NonceModelAdmin(admin.ModelAdmin):
    list_display = ("value", "context", "not_on_or_after")
admin.site.register(Nonce, NonceModelAdmin)
class AttributeValueAdmin(admin.ModelAdmin):
    list_display = ('content_type', 'owner', 'attribute',
            'content')
admin.site.register(models.AttributeValue, AttributeValueAdmin)
class FederatedIdAdmin(admin.ModelAdmin):
    list_display = ('provider', 'about', 'service', 'id_format', 'id_value')
    list_filter = ('provider', 'about', 'service', 'id_format')

admin.site.register(models.FederatedId, FederatedIdAdmin)
class LogoutUrlAdmin(admin.ModelAdmin):
    list_display = ('provider', 'logout_url', 'logout_use_iframe', 'logout_use_iframe_timeout')
admin.site.register(models.LogoutUrl, LogoutUrlAdmin)
class AuthenticationEventAdmin(admin.ModelAdmin):
    list_display = ('when', 'who', 'how', 'nonce')
    list_filter = ('how',)
    date_hierarchy = 'when'
    search_fields = ('who', 'nonce', 'how')

admin.site.register(models.AuthenticationEvent, AuthenticationEventAdmin)
class UserExternalIdAdmin(admin.ModelAdmin):
    list_display = ('user', 'source', 'external_id', 'created', 'updated')
    list_filter = ('source',)
    date_hierarchy = 'created'
    search_fields = ('user__username', 'source', 'external_id')
admin.site.register(models.UserExternalId, UserExternalIdAdmin)
class DeletedUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'creation')
    date_hierarchy = 'creation'
admin.site.register(models.DeletedUser, DeletedUserAdmin)

DB_SESSION_ENGINES = (
    'django.contrib.sessions.backends.db',
    'django.contrib.sessions.backends.cached_db',
)

if settings.SESSION_ENGINE in DB_SESSION_ENGINES:
    class SessionAdmin(admin.ModelAdmin):
        def _session_data(self, obj):
            return pprint.pformat(obj.get_decoded()).replace('\n', '<br>\n')
        _session_data.allow_tags = True
        _session_data.short_description = _('session data')
        list_display = ['session_key', 'ips', 'user', '_session_data', 'expire_date']
        fields = ['session_key', 'ips', 'user', '_session_data', 'expire_date']
        readonly_fields = ['ips', 'user', '_session_data']
        date_hierarchy = 'expire_date'
        actions = ['clear_expired']

        def ips(self, session):
            content = session.get_decoded()
            ips = content.get('ips', set())
            return ', '.join(ips)
        ips.short_description = _('IP adresses')

        def user(self, session):
            from django.contrib import auth
            from django.contrib.auth import models as auth_models
            content = session.get_decoded()
            if auth.SESSION_KEY not in content:
                return
            user_id = content[auth.SESSION_KEY]
            if auth.BACKEND_SESSION_KEY not in content:
                return
            backend_class = content[auth.BACKEND_SESSION_KEY]
            backend = auth.load_backend(backend_class)
            try:
                user = backend.get_user(user_id) or auth_models.AnonymousUser()
            except:
                user = _('deleted user %r') % user_id
            return user
        user.short_description = _('user')

        def clear_expired(self, request, queryset):
            queryset.filter(expire_date__lt=timezone.now()).delete()
        clear_expired.short_description = _('clear expired sessions')

    admin.site.register(Session, SessionAdmin)

class ExternalUserListFilter(admin.SimpleListFilter):
    title = _('external')

    parameter_name = 'external'

    def lookups(self, request, model_admin):
        return (
                ('1', _('Yes')),
                ('0', _('No'))
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == '1':
            return queryset.filter(userexternalid__isnull=False)
        elif self.value() == '0':
            return queryset.filter(userexternalid__isnull=True)
        return queryset

class UserRealmListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('realm')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'realm'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return app_settings.REALMS

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value():
            return queryset.filter(username__endswith=u'@' + self.value())
        return queryset

class AuthenticUserAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    form = admin_forms.UserChangeForm
    add_form = admin_forms.UserCreationForm
    add_fieldsets = (
            (None, {
                'classes': ('wide',),
                'fields': ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')}
            ),
        )
    list_filter = UserAdmin.list_filter + (UserRealmListFilter,ExternalUserListFilter)

    def get_fieldsets(self, request, obj=None):
        fieldsets = deepcopy(super(AuthenticUserAdmin, self).get_fieldsets(request, obj))
        if obj:
            if not request.user.is_superuser:
                fieldsets[2][1]['fields'] = filter(lambda x: x !=
                        'is_superuser', fieldsets[2][1]['fields'])
            qs = models.Attribute.objects.all()
            insertion_idx = 2
        else:
            qs = models.Attribute.objects.filter(required=True)
            insertion_idx = 1
        if qs.exists():
            fieldsets = list(fieldsets)
            fieldsets.insert(insertion_idx, 
                    (_('Attributes'), {'fields': [at.name for at in qs]}))
        return fieldsets

    def get_form(self, request, obj=None, **kwargs):
        if 'fields' in kwargs:
            fields = kwargs.pop('fields')
        else:
            fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        if obj:
            qs = models.Attribute.objects.all()
        else:
            qs = models.Attribute.objects.filter(required=True)
        non_model_fields = [a.name for a in qs]
        fields = list(set(fields) - set(non_model_fields))
        kwargs['fields'] = fields
        return super(AuthenticUserAdmin, self).get_form(request, obj=obj, **kwargs)

User = compat.get_user_model()
if User.__module__ == 'django.contrib.auth.models':
    if User in admin.site._registry:
        admin.site.unregister(User)
    admin.site.register(User, AuthenticUserAdmin)

class AttributeAdmin(admin.ModelAdmin):
    list_display = ('label', 'name', 'kind', 'required',
            'asked_on_registration', 'user_editable',
            'user_visible')

admin.site.register(models.Attribute, AttributeAdmin)


class A2GroupAdmin(GroupAdmin):
    form = forms.GroupAdminForm


admin.site.unregister(Group)
admin.site.register(Group, A2GroupAdmin)


@never_cache
def login(request, extra_context=None):
    query = urlencode({REDIRECT_FIELD_NAME: request.get_full_path()})
    url = '{0}?{1}'.format(settings.LOGIN_URL, query)
    return HttpResponseRedirect(url)

admin.site.login = login

@never_cache
def logout(request, extra_context=None):
    query = urlencode({REDIRECT_FIELD_NAME: request.get_full_path()})
    url = '{0}?{1}'.format(settings.LOGOUT_URL, query)
    return HttpResponseRedirect(url)

admin.site.logout = logout

admin.site.register(models.PasswordReset)
