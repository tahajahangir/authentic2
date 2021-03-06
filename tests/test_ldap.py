# -*- coding: utf-8 -*-
import pytest
import mock

import ldap
from ldap.dn import escape_dn_chars
import ldap

from ldaptools.slapd import Slapd, has_slapd
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core import mail
from django.utils.encoding import force_text

from authentic2.a2_rbac.utils import get_default_ou
from django_rbac.utils import get_ou_model
from authentic2.backends import ldap_backend
from authentic2 import crypto

import utils

pytestmark = pytest.mark.skipunless(has_slapd(), reason='slapd is not installed')

USERNAME = u'etienne.michu'
UID = 'etienne.michu'
CN = 'Étienne Michu'
DN = 'cn=%s,o=ôrga' % escape_dn_chars(CN)
PASS = 'passé'
EMAIL = 'etienne.michu@example.net'


@pytest.fixture
def slapd(request):
    slapd = Slapd()
    slapd.add_db('o=ôrga')
    slapd.add_ldif('''dn: o=ôrga
objectClass: organization
o: ôrga

dn: {dn}
objectClass: inetOrgPerson
userPassword: {password}
uid: {uid}
cn: Étienne Michu
sn: Michu
gn: Étienne
mail: etienne.michu@example.net

dn: cn=group1,o=ôrga
objectClass: groupOfNames
member: {dn}

'''.format(dn=DN, uid=UID, password=PASS))
    for i in range(100):
        slapd.add_ldif('''dn: uid=michu{i},o=ôrga
objectClass: inetOrgPerson
userPassword: {password}
uid: michu{i}
cn: Étienne Michu
sn: Michu
gn: Étienne
mail: etienne.michu@example.net

'''.format(i=i, password=PASS))
    group_ldif = '''dn: cn=group2,o=ôrga
gidNumber: 10
objectClass: posixGroup
memberUid: {uid}
'''.format(uid=UID)
    for i in range(100):
        group_ldif += 'memberUid: michu{i}\n'.format(i=i)
    group_ldif += '\n\n'
    slapd.add_ldif(group_ldif)

    def finalize():
        slapd.clean()
    request.addfinalizer(finalize)
    return slapd


def test_connection(slapd):
    conn = slapd.get_connection()
    conn.simple_bind_s(DN, PASS)


@pytest.mark.django_db
def test_simple(slapd, settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': USERNAME,
                                     'password': PASS}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == u'%s@ldap' % USERNAME
    assert user.first_name == u'Étienne'
    assert user.last_name == 'Michu'
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.is_staff is False
    assert user.groups.count() == 0
    assert user.ou == get_default_ou()
    assert not user.check_password(PASS)
    assert 'password' not in client.session['ldap-data']


@pytest.mark.django_db
def test_simple_with_binddn(slapd, settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'binddn': force_text(DN),
        'bindpw': PASS,
        'basedn': u'o=ôrga',
        'use_tls': False,
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': USERNAME,
                                     'password': PASS}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == u'%s@ldap' % USERNAME
    assert user.first_name == u'Étienne'
    assert user.last_name == 'Michu'
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.is_staff is False
    assert user.groups.count() == 0
    assert user.ou == get_default_ou()
    assert not user.check_password(PASS)
    assert 'password' not in client.session['ldap-data']

@pytest.mark.django_db
def test_double_login(slapd, simple_user, settings, app):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'is_superuser': True,
        'is_staff': True,
    }]
    utils.login(app, simple_user, path='/admin/')
    utils.login(app, UID, password=PASS, path='/admin/')


@pytest.mark.django_db
def test_keep_password_in_session(slapd, settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'keep_password_in_session': True,
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': USERNAME,
                                     'password': PASS.decode('utf-8')}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == u'%s@ldap' % USERNAME
    assert user.first_name == u'Étienne'
    assert user.last_name == 'Michu'
    assert user.ou == get_default_ou()
    assert not user.check_password(PASS)
    assert client.session['ldap-data']['password']
    assert DN in result.context['request'].user.ldap_data['password']
    assert crypto.aes_base64_decrypt(
        settings.SECRET_KEY, result.context['request'].user.ldap_data['password'][DN]) == PASS


@pytest.mark.django_db
def test_custom_ou(slapd, settings, client):
    OU = get_ou_model()
    ou = OU.objects.create(name='test', slug='test')
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'ou_slug': 'test',
    }]
    result = client.post('/login/', {'login-password-submit': '1',
                                     'username': USERNAME,
                                     'password': PASS}, follow=True)
    assert result.status_code == 200
    assert 'Étienne Michu' in str(result)
    User = get_user_model()
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == u'%s@ldap' % USERNAME
    assert user.first_name == u'Étienne'
    assert user.last_name == u'Michu'
    assert user.ou == ou
    assert not user.check_password(PASS)


@pytest.mark.django_db
def test_wrong_ou(slapd, settings, client):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'ou_slug': 'test',
    }]
    with pytest.raises(ImproperlyConfigured):
        client.post('/login/', {'login-password-submit': '1',
                                'username': USERNAME,
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
def test_group_mapping(slapd, settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            [u'cn=group1,o=ôrga', ['Group1']],
        ],
    }]
    assert Group.objects.filter(name='Group1').count() == 0
    response = client.post('/login/', {'login-password-submit': '1',
                                       'username': USERNAME,
                                       'password': PASS}, follow=True)
    assert Group.objects.filter(name='Group1').count() == 1
    assert response.context['user'].username == u'%s@ldap' % USERNAME
    assert response.context['user'].groups.count() == 1


@pytest.mark.django_db
def test_posix_group_mapping(slapd, settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            [u'cn=group2,o=ôrga', ['Group2']],
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
    }]
    assert Group.objects.filter(name='Group2').count() == 0
    response = client.post('/login/', {'login-password-submit': '1',
                                       'username': USERNAME,
                                       'password': PASS}, follow=True)
    assert Group.objects.filter(name='Group2').count() == 1
    assert response.context['user'].username == u'%s@ldap' % USERNAME
    assert response.context['user'].groups.count() == 1


@pytest.mark.django_db
def test_group_to_role_mapping(slapd, settings, client):
    from authentic2.a2_rbac.models import Role

    Role.objects.get_or_create(name='Role1')
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'group_to_role_mapping': [
            ['cn=group1,o=ôrga', ['Role1']],
        ],
    }]
    response = client.post('/login/', {'login-password-submit': '1',
                                       'username': USERNAME,
                                       'password': PASS}, follow=True)
    assert response.context['user'].username == u'%s@ldap' % USERNAME
    assert response.context['user'].roles.count() == 1


@pytest.mark.django_db
def test_posix_group_to_role_mapping(slapd, settings, client):
    from authentic2.a2_rbac.models import Role

    Role.objects.get_or_create(name='Role2')
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'group_to_role_mapping': [
            ['cn=group2,o=ôrga', ['Role2']],
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
    }]
    response = client.post('/login/', {'login-password-submit': '1',
                                       'username': USERNAME,
                                       'password': PASS}, follow=True)
    assert response.context['user'].username == u'%s@ldap' % USERNAME
    assert response.context['user'].roles.count() == 1


@pytest.mark.django_db
def test_group_su(slapd, settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': 'o=ôrga',
        'use_tls': False,
        'groupsu': [u'cn=group1,o=ôrga'],
    }]
    response = client.post('/login/', {'login-password-submit': '1',
                                       'username': USERNAME,
                                       'password': PASS}, follow=True)
    assert Group.objects.count() == 0
    assert response.context['user'].username == u'%s@ldap' % USERNAME
    assert response.context['user'].is_superuser
    assert not response.context['user'].is_staff


@pytest.mark.django_db
def test_group_staff(slapd, settings, client):
    from django.contrib.auth.models import Group

    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'groupstaff': [u'cn=group1,o=ôrga'],
    }]
    response = client.post('/login/', {'login-password-submit': '1',
                                       'username': 'etienne.michu',
                                       'password': PASS}, follow=True)
    assert Group.objects.count() == 0
    assert response.context['user'].username == u'%s@ldap' % USERNAME
    assert response.context['user'].is_staff
    assert not response.context['user'].is_superuser


@pytest.mark.django_db
def test_get_users(slapd, settings):
    import django.db.models.base
    from types import MethodType

    User = get_user_model()
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            [u'cn=group2,o=ôrga', ['Group2']],
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
    }]
    save = mock.Mock(wraps=ldap_backend.LDAPUser.save)
    ldap_backend.LDAPUser.save = MethodType(save, None, ldap_backend.LDAPUser)
    bulk_create = mock.Mock(wraps=django.db.models.query.QuerySet.bulk_create)
    django.db.models.query.QuerySet.bulk_create = MethodType(bulk_create, None,
                                                             django.db.models.query.QuerySet)

    # Provision all users and their groups
    assert User.objects.count() == 0
    users = list(ldap_backend.LDAPBackend.get_users())
    assert len(users) == 101
    assert User.objects.count() == 101
    assert bulk_create.call_count == 101
    assert save.call_count == 303

    # Check that if nothing changed no save() is made
    save.reset_mock()
    bulk_create.reset_mock()
    users = list(ldap_backend.LDAPBackend.get_users())
    assert save.call_count == 0
    assert bulk_create.call_count == 0

    # Check that if we delete 1 user, only this user is created
    save.reset_mock()
    bulk_create.reset_mock()
    User.objects.last().delete()
    assert User.objects.count() == 100
    users = list(ldap_backend.LDAPBackend.get_users())
    assert len(users) == 101
    assert User.objects.count() == 101
    assert save.call_count == 3
    assert bulk_create.call_count == 1


@pytest.mark.django_db
def test_set_mandatory_roles(slapd, settings):
    from authentic2.a2_rbac.models import Role

    Role.objects.get_or_create(name='tech')
    Role.objects.get_or_create(name='admin')
    User = get_user_model()
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            [u'cn=group2,o=ôrga', ['Group2']],
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
        'set_mandatory_roles': ['tech', 'admin'],
    }]

    list(ldap_backend.LDAPBackend.get_users())
    assert User.objects.first().roles.count() == 2


@pytest.mark.django_db
def test_nocreate_mandatory_roles(slapd, settings):
    User = get_user_model()
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            [u'cn=group2,o=ôrga', ['Group2']],
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
        'set_mandatory_roles': ['tech', 'admin'],
    }]

    list(ldap_backend.LDAPBackend.get_users())
    assert User.objects.first().roles.count() == 0


@pytest.fixture
def slapd_strict_acl(slapd):
    # forbid modifications by user themselves
    conn = slapd.get_connection_external()
    result = conn.search_s(
        'cn=config',
        ldap.SCOPE_SUBTREE,
        'olcSuffix=o=ôrga')
    dn = result[0][0]
    conn.modify_s(
        dn,
        [
            (ldap.MOD_REPLACE, 'olcAccess', [
                '{0}to * by dn.subtree="o=ôrga" none by * manage'
            ])
        ])
    return slapd


def test_no_connect_with_user_credentials(slapd_strict_acl, db, settings, app):
    slapd = slapd_strict_acl
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'basedn': u'o=ôrga',
        'use_tls': False,
        'create_group': True,
        'group_mapping': [
            ['cn=group2,o=ôrga', ['Group2']],
        ],
        'group_filter': '(&(memberUid={uid})(objectClass=posixGroup))',
        'set_mandatory_roles': ['tech', 'admin'],
    }]
    response = app.get('/login/')
    response.form.set('username', USERNAME)
    response.form.set('password', PASS)
    response = response.form.submit('login-password-submit')
    assert response.status_code == 200
    assert 'Étienne Michu' not in response.body

    settings.LDAP_AUTH_SETTINGS[0]['connect_with_user_credentials'] = False
    response = app.get('/login/')
    response.form.set('username', USERNAME)
    response.form.set('password', PASS)
    response = response.form.submit('login-password-submit').follow()
    assert 'Étienne Michu' in response.body


def test_reset_password_ldap_user(slapd, settings, app, db):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'binddn': force_text(slapd.root_bind_dn),
        'bindpw': force_text(slapd.root_bind_password),
        'basedn': u'o=ôrga',
        'use_tls': False,
    }]
    User = get_user_model()
    assert User.objects.count() == 0
    # first login
    response = app.get('/login/')
    response.form['username'] = USERNAME
    response.form['password'] = PASS
    response = response.form.submit('login-password-submit').follow()
    assert User.objects.count() == 1
    assert 'Étienne Michu' in str(response)
    user = User.objects.get()
    assert user.email == EMAIL
    # logout
    response = response.click('Logout')
    if response.status_code == 200:  # Django 1.7, same_origin is bugged; localhost != localhost:80
        response = response.form.submit().maybe_follow()
    else:
        response = response.maybe_follow()
    response = response.click('Reset it!')
    response.form['email'] = EMAIL
    assert len(mail.outbox) == 0
    response = response.form.submit().maybe_follow()
    assert len(mail.outbox) == 1
    reset_email_url = utils.get_link_from_mail(mail.outbox[0])
    response = app.get(reset_email_url, status=302)
    response = response.maybe_follow()
    assert 'login-password-submit' in response.content
    settings.LDAP_AUTH_SETTINGS[0]['can_reset_password'] = True
    response = app.get(reset_email_url, status=200)
    new_password = 'Aa1xxxxx'
    response.form['new_password1'] = new_password
    response.form['new_password2'] = new_password
    response = response.form.submit(status=302).maybe_follow()
    # verify password has changed
    slapd.get_connection().bind_s(DN, new_password)
    with pytest.raises(ldap.INVALID_CREDENTIALS):
        slapd.get_connection().bind_s(DN, PASS)
    assert not User.objects.get().has_usable_password()


def test_user_cannot_change_password(slapd, settings, app, db):
    settings.LDAP_AUTH_SETTINGS = [{
        'url': [slapd.ldap_url],
        'binddn': force_text(slapd.root_bind_dn),
        'bindpw': force_text(slapd.root_bind_password),
        'basedn': u'o=ôrga',
        'use_tls': False,
        'user_can_change_password': False,
    }]
    User = get_user_model()
    assert User.objects.count() == 0
    # first login
    response = app.get('/login/')
    response.form['username'] = USERNAME
    response.form['password'] = PASS
    response = response.form.submit('login-password-submit').follow()
    response = response.click('Your account')
    assert 'Password' not in response
    response = app.get('/accounts/password/change/')
    assert response['Location'].endswith('/accounts/')
