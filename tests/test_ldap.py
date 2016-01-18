# -*- coding: utf-8 -*-
import pytest

from authentic2_provisionning_ldap.ldap_utils import Slapd, has_slapd
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from authentic2.a2_rbac.utils import get_default_ou
from django_rbac.utils import get_ou_model
from authentic2.backends import ldap_backend
from authentic2 import crypto

pytestmark = pytest.mark.skipunless(has_slapd(), reason='slapd is not installed')

slapd = None

DN = 'uid=etienne.michu,o=orga'
UID = 'etienne.michu'
PASS = 'pass'

def setup_module(module):
    global slapd
    slapd = Slapd()
    slapd.add_ldif('''dn: {dn}
objectClass: inetOrgPerson
userPassword: {password}
uid: {uid}
cn: Étienne Michu
sn: Michu
gn: Étienne
mail: etienne.michu@example.net

dn: cn=group1,o=orga
objectClass: groupOfNames
member: {dn}

dn: cn=group2,o=orga
gidNumber: 10
objectClass: posixGroup
memberUid: {uid}
'''.format(dn=DN, uid=UID, password=PASS))


def teardown_module(module):
    slapd.clean()


def setup_function(function):
    slapd.checkpoint()


def teardown_function(function):
    slapd.restore()


def test_connection():
    conn = slapd.get_connection()
    conn.simple_bind_s(DN, PASS)


@pytest.mark.django_db
def test_simple(settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == 'etienne.michu@ldap'
    assert user.first_name == u'Étienne'
    assert user.last_name == 'Michu'
    assert user.ou == get_default_ou()
    assert not user.check_password(PASS)
    assert ldap_backend.LDAPUser.SESSION_PASSWORD_KEY not in client.session

@pytest.mark.django_db
def test_keep_password_in_session(settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'keep_password_in_session': True,
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == 'etienne.michu@ldap'
    assert user.first_name == u'Étienne'
    assert user.last_name == 'Michu'
    assert user.ou == get_default_ou()
    assert not user.check_password(PASS)
    assert ldap_backend.LDAPUser.SESSION_PASSWORD_KEY in client.session
    assert DN in client.session[ldap_backend.LDAPUser.SESSION_PASSWORD_KEY]
    assert crypto.aes_base64_decrypt(
        settings.SECRET_KEY, client.session[ldap_backend.LDAPUser.SESSION_PASSWORD_KEY][DN]) == PASS

@pytest.mark.django_db
def test_custom_ou(settings, client):
    OU = get_ou_model()
    ou = OU.objects.create(name='test', slug='test')
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'ou_slug': 'test',
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == u'etienne.michu@ldap'
    assert user.first_name == u'Étienne'
    assert user.last_name == u'Michu'
    assert user.ou == ou
    assert not user.check_password(PASS)


@pytest.mark.django_db
def test_wrong_ou(settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'ou_slug': 'test',
    }]
    with pytest.raises(ImproperlyConfigured):
        result = client.post('/login/', {'login-password-submit': '1',
                                         'username': 'etienne.michu',
                                         'password': PASS}, follow=True)


def test_dn_formatter():
    from authentic2.ldap_utils import DnFormatter, FilterFormatter
    formatter = FilterFormatter()

    assert formatter.format('uid={uid}', uid='john doe') == 'uid=john doe'
    assert formatter.format('uid={uid}', uid='(#$!"?éé') == 'uid=\\28#$!"?éé'
    assert formatter.format('uid={uid}', uid=['(#$!"?éé']) == 'uid=\\28#$!"?éé'
    assert formatter.format('uid={uid}', uid=('(#$!"?éé',)) == 'uid=\\28#$!"?éé'

    formatter = DnFormatter()

    assert formatter.format('uid={uid}', uid='john doé!#$"\'-_') == 'uid=john doé!#$\\"\'-_'
    assert formatter.format('uid={uid}', uid=['john doé!#$"\'-_']) == 'uid=john doé!#$\\"\'-_'


@pytest.mark.django_db
def test_group_mapping(settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            ('cn=group1,o=orga', ['Group1']),
        ],
    }]
    assert Group.objects.filter(name='Group1').count() == 0
    response = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert Group.objects.filter(name='Group1').count() == 1
    assert response.context['user'].username == 'etienne.michu@ldap'
    assert response.context['user'].groups.count() == 1


@pytest.mark.django_db
def test_posix_group_mapping(settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            ('cn=group2,o=orga', ['Group2']),
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
    }]
    assert Group.objects.filter(name='Group2').count() == 0
    response = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert Group.objects.filter(name='Group2').count() == 1
    assert response.context['user'].username == 'etienne.michu@ldap'
    assert response.context['user'].groups.count() == 1


@pytest.mark.django_db
def test_group_su(settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'groupsu': ['cn=group1,o=orga'],
    }]
    response = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert Group.objects.count() == 0
    assert response.context['user'].username == 'etienne.michu@ldap'
    assert response.context['user'].is_superuser
    assert not response.context['user'].is_staff


@pytest.mark.django_db
def test_group_staff(settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldapi_url],
        'basedn': 'o=orga',
        'use_tls': False,
        'groupstaff': ['cn=group1,o=orga'],
    }]
    response = client.post('/login/', {'login-password-submit': '1',
                                     'username': 'etienne.michu',
                                     'password': PASS}, follow=True)
    assert Group.objects.count() == 0
    assert response.context['user'].username == 'etienne.michu@ldap'
    assert response.context['user'].is_staff
    assert not response.context['user'].is_superuser
