from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^accounts/oidc/login/(?P<pk>\d+)/$', views.oidc_login, name='oidc-login'),
    url(r'^accounts/oidc/login/$', views.login_initiate, name='oidc-login-initiate'),
    url(r'^accounts/oidc/callback/$', views.login_callback, name='oidc-login-callback'),
]
