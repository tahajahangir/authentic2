from django.conf.urls import url
from .views import (handle_request, post_account_linking, delete_certificate,
        error_ssl)

urlpatterns = [
    url(r'^$',
        handle_request,
        name='user_signin_ssl'),
    url(r'^post_account_linking/$',
        post_account_linking,
        name='post_account_linking'),
    url(r'^delete_certificate/(?P<certificate_pk>\d+)/$',
        delete_certificate,
        name='delete_certificate'),
    url(r'^error_ssl/$',
        error_ssl,
        name='error_ssl'),
]
