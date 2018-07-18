from django.utils.translation import gettext_noop
from django.shortcuts import render

from . import app_settings, utils


class OIDCFrontend(object):
    def enabled(self):
        return app_settings.ENABLE and utils.has_providers()

    def name(self):
        return gettext_noop('OpenIDConnect')

    def id(self):
        return 'oidc'

    def login(self, request, *args, **kwargs):
        context = kwargs.get('context', {})
        context['providers'] = utils.get_providers(shown=True)
        return render(request, 'authentic2_auth_oidc/login.html', context)
