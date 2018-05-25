from django.conf.urls import url, include
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.views import serve

from . import app_settings, plugins, views

admin.autodiscover()

handler500 = 'authentic2.views.server_error'

urlpatterns = [
    url(r'^$', views.homepage, name='auth_homepage'),
    url(r'test_redirect/$', views.test_redirect)
]

not_homepage_patterns = [
    url(r'^login/$', views.login, name='auth_login'),
    url(r'^logout/$', views.logout, name='auth_logout'),
    url(r'^redirect/(.*)', views.redirect, name='auth_redirect'),
    url(r'^accounts/', include('authentic2.profile_urls'))
]

not_homepage_patterns += [
    url(r'^accounts/', include(app_settings.A2_REGISTRATION_URLCONF)),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^admin_tools/', include('admin_tools.urls')),
    url(r'^idp/', include('authentic2.idp.urls')),
    url(r'^manage/', include('authentic2.manager.urls')),
    url(r'^api/', include('authentic2.api_urls'))
]


urlpatterns += not_homepage_patterns

try:
    if getattr(settings, 'DISCO_SERVICE', False):
        urlpatterns += [
            (r'^disco_service/', include('disco_service.disco_responder')),
        ]
except:
    pass

if settings.DEBUG:
    urlpatterns += [
        url(r'^static/(?P<path>.*)$', serve)
    ]

if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

urlpatterns = plugins.register_plugins_urls(urlpatterns)
