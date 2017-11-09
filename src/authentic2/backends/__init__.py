from django.contrib.auth import get_user_model
from authentic2 import app_settings


def get_user_queryset():
    User = get_user_model()

    qs = User.objects.all()

    if app_settings.A2_USER_FILTER:
        qs = qs.filter(**app_settings.A2_USER_FILTER)

    if app_settings.A2_USER_EXCLUDE:
        qs = qs.exclude(**app_settings.A2_USER_EXCLUDE)

    return qs


def is_user_authenticable(user):
    # if user is None, don't care about the authenticable status
    if user is None:
        return True
    if not app_settings.A2_USER_FILTER and not app_settings.A2_USER_EXCLUDE:
        return True
    return get_user_queryset().filter(pk=user.pk).exists()


from .ldap_backend import LDAPBackend
from .models_backend import ModelBackend
