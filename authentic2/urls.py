from django.conf.urls import patterns, url, include
from django.conf import settings
from django.contrib import admin

from . import app_settings, plugins

admin.autodiscover()

handler500 = 'authentic2.views.server_error'

urlpatterns = patterns('authentic2.views', url(r'^$', 'homepage',
    name='auth_homepage'))

not_homepage_patterns = patterns('authentic2.views',
    url(r'^login/$', 'login', name='auth_login'),
    url(r'^logout/$', 'logout', name='auth_logout'),
    url(r'^redirect/(.*)', 'redirect', name='auth_redirect'),
    url(r'^accounts/', include('authentic2.profile_urls')),
)

not_homepage_patterns += patterns('',
    url(r'^accounts/', include(app_settings.A2_REGISTRATION_URLCONF)),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^admin_tools/', include('admin_tools.urls')),
    url(r'^idp/', include('authentic2.idp.urls')),
)

if settings.AUTH_OPENID:
    not_homepage_patterns += patterns('',
        (r'^accounts/openid/',
            include('authentic2.auth2_auth.auth2_openid.urls')),
    )

if settings.AUTH_SSL:
    not_homepage_patterns += patterns('',
        url(r'^sslauth/', include('authentic2.auth2_auth.auth2_ssl.urls')))

urlpatterns += not_homepage_patterns

urlpatterns += patterns('',
    (r'^authsaml2/', include('authentic2.authsaml2.urls')),
)

try:
    if settings.DISCO_SERVICE:
        urlpatterns += patterns('',
            (r'^disco_service/', include('disco_service.disco_responder')),
        )
except:
    pass

urlpatterns = plugins.register_plugins_urls('authentic2.plugin', urlpatterns)
