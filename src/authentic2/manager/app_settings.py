import sys


class AppSettings(object):
    __PREFIX = 'A2_MANAGER_'
    __DEFAULTS = {
        'HOMEPAGE_URL': None,
        'ROLE_FORM_CLASS': None,
        'SHOW_ALL_OU': True,
        'ROLE_MEMBERS_FROM_OU': False,
        'SHOW_INTERNAL_ROLES': False,
        'USER_SEARCH_MINIMUM_CHARS': 0,
        'LOGIN_URL': None,
        'SITE_TITLE': None,
    }

    def __getattr__(self, name):
        from django.conf import settings
        if name not in self.__DEFAULTS:
            raise AttributeError
        return getattr(settings, self.__PREFIX + name, self.__DEFAULTS[name])

app_settings = AppSettings()
app_settings.__name__ = __name__
sys.modules[__name__] = app_settings
