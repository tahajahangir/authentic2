from django.conf.urls.defaults import patterns, include

from .saml import saml2_endpoints

from django.conf import settings
from interactions import consent_federation, consent_attributes

urlpatterns = patterns('',)

if settings.IDP_SAML2:
    urlpatterns += patterns('',
        (r'^saml2/', include(saml2_endpoints)),)

if settings.IDP_CAS:
    from authentic2.idp.idp_cas.views import Authentic2CasProvider
    urlpatterns += patterns('',
            ('^cas/', include(Authentic2CasProvider().url)))

urlpatterns += patterns('',
        (r'^consent_federation', consent_federation),
        (r'^consent_attributes', consent_attributes),)
