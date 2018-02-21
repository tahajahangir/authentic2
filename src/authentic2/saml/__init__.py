from django.apps import AppConfig

default_app_config = 'authentic2.saml.A2SAMLAppConfig'


class A2SAMLAppConfig(AppConfig):
    name = 'authentic2.saml'

    def a2_hook_good_next_url(self, next_url):
        from .utils import saml_good_next_url
        return saml_good_next_url(next_url)
