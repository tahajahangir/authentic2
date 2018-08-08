from django import forms
from django.contrib import admin
from django.utils.functional import curry

from authentic2.attributes_ng.engine import get_service_attributes

from . import models


class OIDCClaimInlineForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(OIDCClaimInlineForm, self).__init__(*args, **kwargs)
        choices = get_service_attributes(self.instance.client_id)
        self.fields['value'].choices = choices
        self.fields['value'].widget = forms.Select(choices=choices)

    class Meta:
        model = models.OIDCClaim
        fields = ['name', 'value', 'scopes']


class OIDCClaimInlineAdmin(admin.TabularInline):

    model = models.OIDCClaim
    form = OIDCClaimInlineForm
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        initial = []
        # formsets are only saved if formset.has_changed() is True, so only set initial
        # values on the GET (display of the creation form)
        if request.method == 'GET' and not obj:
            initial.extend([
                {'name': 'preferred_username', 'value': 'django_user_identifier', 'scopes': 'profile'},
                {'name': 'given_name', 'value': 'django_user_first_name', 'scopes': 'profile'},
                {'name': 'family_name', 'value': 'django_user_last_name', 'scopes': 'profile'},
                {'name': 'email', 'value': 'django_user_email', 'scopes': 'email'},
                {'name': 'email_verified', 'value': 'django_user_email_verified', 'scopes': 'email'},
            ])
            self.extra = 5
        formset = super(OIDCClaimInlineAdmin, self).get_formset(request, obj=obj, **kwargs)
        formset.__init__ = curry(formset.__init__, initial=initial)
        return formset


class OIDCClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'client_id', 'ou', 'identifier_policy', 'created', 'modified']
    list_filter = ['ou', 'identifier_policy']
    date_hierarchy = 'modified'
    readonly_fields = ['created', 'modified']
    inlines = [OIDCClaimInlineAdmin]


class OIDCAuthorizationAdmin(admin.ModelAdmin):
    list_display = ['client', 'user', 'created', 'expired']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'user__username']
    date_hierarchy = 'created'
    readonly_fields = ['created', 'expired']

    def get_queryset(self, request):
        qs = super(OIDCAuthorizationAdmin, self).get_queryset(request)
        qs = qs.prefetch_related('client')
        return qs

    def get_search_results(self, request, queryset, search_term):
            from django.contrib.contenttypes.models import ContentType
            from authentic2.a2_rbac.models import OrganizationalUnit as OU

            queryset, use_distinct = super(OIDCAuthorizationAdmin, self).get_search_results(
                request, queryset, search_term)
            clients = models.OIDCClient.objects.filter(name__contains=search_term).values_list('pk')
            ous = OU.objects.filter(name__contains=search_term).values_list('pk')
            queryset |= self.model.objects.filter(
                client_ct=ContentType.objects.get_for_model(models.OIDCClient),
                client_id=clients)
            queryset |= self.model.objects.filter(
                client_ct=ContentType.objects.get_for_model(OU),
                client_id=ous)
            return queryset, use_distinct


class OIDCCodeAdmin(admin.ModelAdmin):
    list_display = ['client', 'user', 'uuid', 'created', 'expired']
    list_filter = ['client']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'user__username',
                     'client__name']
    date_hierarchy = 'created'
    readonly_fields = ['uuid', 'created', 'expired', 'user', 'uuid', 'client', 'state', 'nonce']


class OIDCAccessTokenAdmin(admin.ModelAdmin):
    list_display = ['client', 'user', 'uuid', 'created', 'expired']
    list_filter = ['client']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'user__username',
                     'client__name']
    date_hierarchy = 'created'
    readonly_fields = ['uuid', 'created', 'expired']


admin.site.register(models.OIDCClient, OIDCClientAdmin)
admin.site.register(models.OIDCAuthorization, OIDCAuthorizationAdmin)
admin.site.register(models.OIDCCode, OIDCCodeAdmin)
admin.site.register(models.OIDCAccessToken, OIDCAccessTokenAdmin)
