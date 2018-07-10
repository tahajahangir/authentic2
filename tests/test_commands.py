import datetime
import importlib
import json

from django.core import management
import py

from authentic2.models import Attribute, DeletedUser
from authentic2_auth_oidc.models import OIDCProvider
from django_rbac.utils import get_ou_model


def test_changepassword(db, simple_user, monkeypatch):
    import getpass

    def _getpass(*args, **kwargs):
        return 'pass'

    monkeypatch.setattr(getpass, 'getpass', _getpass)
    management.call_command('changepassword', 'user')
    old_pass = simple_user.password
    simple_user.refresh_from_db()
    assert old_pass != simple_user.password


def test_clean_unused_account(simple_user):
    simple_user.last_login = datetime.datetime.now() - datetime.timedelta(days=2)
    simple_user.save()
    management.call_command('clean-unused-accounts', '1')
    assert DeletedUser.objects.get(user=simple_user)


def test_cleanupauthentic(db):
    management.call_command('cleanupauthentic')


def test_load_ldif(db, monkeypatch, tmpdir):
    ldif = tmpdir.join('some.ldif')
    ldif.ensure()

    class MockPArser(object):
        def __init__(self, *args, **kwargs):
            self.users = []
            assert len(args) == 1
            assert isinstance(args[0], file)
            assert kwargs['options']['extra_attribute'] == {'ldap_attr': 'first_name'}
            assert kwargs['options']['result'] == 'result'

        def parse(self):
            pass

    oidc_cmd = importlib.import_module(
        'authentic2.management.commands.load-ldif')
    monkeypatch.setattr(oidc_cmd, 'DjangoUserLDIFParser', MockPArser)
    management.call_command(
        'load-ldif', ldif.strpath, result='result', extra_attribute={'ldap_attr': 'first_name'})

    # test ExtraAttributeAction
    class MockPArser(object):
        def __init__(self, *args, **kwargs):
            self.users = []
            assert len(args) == 1
            assert isinstance(args[0], file)
            assert kwargs['options']['extra_attribute'] == {
                'ldap_attr': Attribute.objects.get(name='first_name')}
            assert kwargs['options']['result'] == 'result'

        def parse(self):
            pass

    monkeypatch.setattr(oidc_cmd, 'DjangoUserLDIFParser', MockPArser)
    management.call_command(
        'load-ldif', '--extra-attribute', 'ldap_attr', 'first_name',
        '--result', 'result', ldif.strpath)


def test_oidc_register_issuer(db, tmpdir, monkeypatch):
    oidc_conf_f = py.path.local(__file__).dirpath('openid_configuration.json')
    with oidc_conf_f.open() as f:
        oidc_conf = json.load(f)

    def register_issuer(
            name, issuer=None, openid_configuration=None, verify=True, timeout=None,
            ou=None):
        OU = get_ou_model()
        ou = OU.objects.get(default=True)
        return OIDCProvider.objects.create(
            name=name, ou=ou, issuer=issuer, strategy='create',
            authorization_endpoint=openid_configuration['authorization_endpoint'],
            token_endpoint=openid_configuration['token_endpoint'],
            userinfo_endpoint=openid_configuration['userinfo_endpoint'],
            end_session_endpoint=openid_configuration['end_session_endpoint'])

    oidc_cmd = importlib.import_module(
        'authentic2_auth_oidc.management.commands.oidc-register-issuer')
    monkeypatch.setattr(oidc_cmd, 'register_issuer', register_issuer)

    oidc_conf = py.path.local(__file__).dirpath('openid_configuration.json').strpath
    management.call_command(
        'oidc-register-issuer', '--openid-configuration', oidc_conf, '--issuer', 'issuer',
        'somename')

    provider = OIDCProvider.objects.get(name='somename')
    assert provider.issuer == 'issuer'


def test_resetpassword(simple_user):
    management.call_command('resetpassword', 'user')
    old_pass = simple_user.password
    simple_user.refresh_from_db()
    assert old_pass != simple_user.password


def test_sync_metadata(db):
    test_file = py.path.local(__file__).dirpath('metadata.xml').strpath
    management.call_command('sync-metadata', test_file)
