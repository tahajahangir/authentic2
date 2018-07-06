import string
import random
import re
import abc

from django.utils.translation import ugettext as _
from django.utils.module_loading import import_string
from . import app_settings


def generate_password():
    '''Generate a password that validates current password policy.

       Beware that A2_PASSWORD_POLICY_REGEX cannot be validated.
    '''
    digits = string.digits
    lower = string.lowercase
    upper = string.uppercase
    punc = string.punctuation

    min_len = max(app_settings.A2_PASSWORD_POLICY_MIN_LENGTH, 8)
    min_class_count = max(app_settings.A2_PASSWORD_POLICY_MIN_CLASSES, 3)
    new_password = []

    while len(new_password) < min_len:
        for cls in (digits, lower, upper, punc)[:min_class_count]:
            new_password.append(random.choice(cls))
    random.shuffle(new_password)
    return ''.join(new_password)


class PasswordChecker(object):
    __metaclass__ = abc.ABCMeta

    class Check(object):
        def __init__(self, label, result):
            self.label = label
            self.result = result

    def __init__(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def __call__(self, password, **kwargs):
        '''Return an iterable of Check objects giving the list of checks and
           their result.'''
        return []


class DefaultPasswordChecker(PasswordChecker):
    @property
    def min_length(self):
        return app_settings.A2_PASSWORD_POLICY_MIN_LENGTH

    @property
    def at_least_one_lowercase(self):
        return app_settings.A2_PASSWORD_POLICY_MIN_CLASSES > 0

    @property
    def at_least_one_digit(self):
        return app_settings.A2_PASSWORD_POLICY_MIN_CLASSES > 1

    @property
    def at_least_one_uppercase(self):
        return app_settings.A2_PASSWORD_POLICY_MIN_CLASSES > 2

    @property
    def regexp(self):
        return app_settings.A2_PASSWORD_POLICY_REGEX

    @property
    def regexp_label(self):
        return app_settings.A2_PASSWORD_POLICY_REGEX_ERROR_MSG

    def __call__(self, password, **kwargs):
        if self.min_length:
            yield self.Check(
                result=len(password) >= self.min_length,
                label=_('%s characters') % self.min_length)

        if self.at_least_one_lowercase:
            yield self.Check(
                result=any(c.islower() for c in password),
                label=_('1 lowercase letter'))

        if self.at_least_one_digit:
            yield self.Check(
                result=any(c.isdigit() for c in password),
                label=_('1 digit'))

        if self.at_least_one_uppercase:
            yield self.Check(
                result=any(c.isupper() for c in password),
                label=_('1 uppercase letter'))

        if self.regexp and self.regexp_label:
            yield self.Check(
                result=bool(re.match(self.regexp, password)),
                label=self.regexp_label)


def get_password_checker(*args, **kwargs):
    return import_string(app_settings.A2_PASSWORD_POLICY_CLASS)(*args, **kwargs)
