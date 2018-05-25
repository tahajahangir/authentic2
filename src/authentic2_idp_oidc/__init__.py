from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

default_app_config = 'authentic2_idp_oidc.apps.AppConfig'


class Plugin(object):
    def get_before_urls(self):
        from . import urls
        return urls.urlpatterns

    def get_apps(self):
        return [__name__]

    def logout_list(self, request):
        from .utils import get_oidc_sessions
        from . import app_settings

        fragments = []

        oidc_sessions = get_oidc_sessions(request)
        for key, value in oidc_sessions.iteritems():
            if 'frontchannel_logout_uri' not in value:
                continue
            ctx = {
                'url': value['frontchannel_logout_uri'],
                'name': value['name'],
                'iframe_timeout': value.get('frontchannel_timeout') or app_settings.DEFAULT_FRONTCHANNEL_TIMEOUT,
            }
            fragments.append(
                render_to_string(
                    'authentic2_idp_oidc/logout_fragment.html',
                    ctx))
        return fragments