import logging

from mellon.backends import SAMLBackend

from authentic2.middleware import StoreRequestMiddleware
from authentic2.backends import is_user_authenticable

from . import app_settings


logger = logging.getLogger(__name__)


class SAMLBackend(SAMLBackend):
    def authenticate(self, saml_attributes, **credentials):
        if not app_settings.enable:
            return None
        user = super(SAMLBackend, self).authenticate(saml_attributes, **credentials)
        if not is_user_authenticable(user):
            logger.error(u'auth_saml: authentication refused by user filters')
            return None
        return user

    def get_saml2_authn_context(self):
        # Pass AuthnContextClassRef from the previous IdP
        request = StoreRequestMiddleware.get_request()
        if request:
            authn_context_class_ref = request.session.get(
                'mellon_session', {}).get('authn_context_class_ref')
            if authn_context_class_ref:
                return authn_context_class_ref

        import lasso
        return lasso.SAML2_AUTHN_CONTEXT_PREVIOUS_SESSION
