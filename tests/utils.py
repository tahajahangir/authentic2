import re
import base64
import urlparse
from contextlib import contextmanager

from lxml import etree
import pytest
from django.test import TestCase
from django.core.urlresolvers import reverse
from django.conf import settings

from authentic2 import utils


skipif_sqlite = pytest.mark.skipif('sqlite' in settings.DATABASES['default']['ENGINE'],
                                   reason='this test does not work with sqlite')


def login(app, user, path=None, password=None, remember_me=None):
    if path:
        login_page = app.get(path, status=302).maybe_follow()
    else:
        login_page = app.get(reverse('auth_login'))
    assert login_page.request.path == reverse('auth_login')
    form = login_page.form
    form.set('username', user.username if hasattr(user, 'username') else user)
    # password is supposed to be the same as username
    form.set('password', password or user.username)
    if remember_me is not None:
        form.set('remember_me', bool(remember_me))
    response = form.submit(name='login-password-submit').follow()
    if path:
        assert response.request.path == path
    else:
        assert response.request.path == reverse('auth_homepage')
    assert '_auth_user_id' in app.session
    return response


def logout(app):
    assert '_auth_user_id' in app.session
    response = app.get(reverse('auth_logout')).maybe_follow()
    response = response.form.submit().maybe_follow()
    if 'continue-link' in response.content:
        response = response.click('Continue logout').maybe_follow()
    assert '_auth_user_id' not in app.session
    return response


def basic_authorization_header(user, password=None):
    cred = base64.b64encode('%s:%s' % (user.username, password or user.username))
    return {'Authorization': 'Basic %s' % cred}


def get_response_form(response, form='form'):
    contexts = list(response.context)
    for c in contexts:
        if form not in c:
            continue
        return c[form]


class Authentic2TestCase(TestCase):
    def assertEqualsURL(self, url1, url2, **kwargs):
        '''Check that url1 is equals to url2 augmented with parameters kwargs
           in its query string.

           The string '*' is a special value, when used it just check that the
           given parameter exist in the first url, it does not check the exact
           value.
        '''
        splitted1 = urlparse.urlsplit(url1)
        url2 = utils.make_url(url2, params=kwargs)
        splitted2 = urlparse.urlsplit(url2)
        for i, (elt1, elt2) in enumerate(zip(splitted1, splitted2)):
            if i == 3:
                elt1 = urlparse.parse_qs(elt1, True)
                elt2 = urlparse.parse_qs(elt2, True)
                for k, v in elt1.items():
                    elt1[k] = set(v)
                for k, v in elt2.items():
                    if v == ['*']:
                        elt2[k] = elt1.get(k, v)
                    else:
                        elt2[k] = set(v)
            self.assertTrue(
                elt1 == elt2,
                "URLs are not equal: %s != %s" % (splitted1, splitted2))

    def assertRedirectsComplex(self, response, expected_url, **kwargs):
        self.assertEquals(response.status_code, 302)
        scheme, netloc, path, query, fragment = urlparse.urlsplit(response.url)
        e_scheme, e_netloc, e_path, e_query, e_fragment = \
            urlparse.urlsplit(expected_url)
        e_scheme = e_scheme if e_scheme else scheme
        e_netloc = e_netloc if e_netloc else netloc
        expected_url = urlparse.urlunsplit((e_scheme, e_netloc, e_path,
                                            e_query, e_fragment))
        self.assertEqualsURL(response['Location'], expected_url, **kwargs)

    def assertXPathConstraints(self, xml, constraints, namespaces):
        if hasattr(xml, 'content'):
            xml = xml.content
        doc = etree.fromstring(xml)
        for xpath, content in constraints:
            nodes = doc.xpath(xpath, namespaces=namespaces)
            self.assertTrue(len(nodes) > 0, 'xpath %s not found' % xpath)
            if isinstance(content, basestring):
                for node in nodes:
                    if hasattr(node, 'text'):
                        self.assertEqual(
                            node.text, content, 'xpath %s does not contain %s but '
                            '%s' % (xpath, content, node.text))
                    else:
                        self.assertEqual(
                            node, content, 'xpath %s does not contain %s but %s' %
                            (xpath, content, node))
            else:
                values = [node.text if hasattr(node, 'text') else node for node in nodes]
                if isinstance(content, set):
                    self.assertEqual(set(values), content)
                elif isinstance(content, list):
                    self.assertEqual(values, content)
                else:
                    raise NotImplementedError('comparing xpath result to type %s: %r is not '
                                              'implemented' % (type(content), content))


@contextmanager
def check_log(caplog, msg):
    idx = len(caplog.records)
    yield
    assert any(msg in record.msg for record in caplog.records[idx:]), \
        '%r not found in log records' % msg


def can_resolve_dns():
    '''Verify that DNS resolving is available'''
    import socket
    try:
        return isinstance(socket.gethostbyname('entrouvert.com'), str)
    except:
        return False


def get_links_from_mail(mail):
    '''Extract links from mail sent by Django'''
    return re.findall('https?://[^ \n]*', mail.body)


def get_link_from_mail(mail):
    '''Extract the first and only link from this mail'''
    links = get_links_from_mail(mail)
    assert links, 'there is not link in this mail'
    assert len(links) == 1, 'there are more than one link in this mail'
    return links[0]


def saml_sp_metadata(base_url):
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<EntityDescriptor
 entityID="{base_url}/"
 xmlns="urn:oasis:names:tc:SAML:2.0:metadata">
 <SPSSODescriptor
   AuthnRequestsSigned="true"
   WantAssertionsSigned="true"
   protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
   <SingleLogoutService
     Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
     Location="https://files.entrouvert.org/mellon/logout" />
   <AssertionConsumerService
     index="0"
     isDefault="true"
     Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
     Location="{base_url}/sso/POST" />
   <AssertionConsumerService
     index="1"
     Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact"
     Location="{base_url}/mellon/artifactResponse" />
 </SPSSODescriptor>
</EntityDescriptor>'''.format(base_url=base_url)
