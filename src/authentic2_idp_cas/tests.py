import urlparse


from django.test.client import RequestFactory, Client
from django.test.utils import override_settings


from authentic2.compat import get_user_model
from authentic2.tests import Authentic2TestCase
from .models import Ticket, Service, Attribute
from . import constants
from authentic2.constants import AUTHENTICATION_EVENTS_SESSION_KEY


@override_settings(A2_IDP_CAS_ENABLE=True)
class CasTests(Authentic2TestCase):
    LOGIN = 'test'
    PASSWORD = 'test'
    EMAIL = 'test@example.com'
    FIRST_NAME = 'John'
    LAST_NAME = 'Doe'
    NAME = 'CAS service'
    SLUG = 'cas-service'
    URL = 'https://casclient.com/'
    NAME2 = 'CAS service2'
    SLUG2 = 'cas-service2'
    URL2 = 'https://casclient2.com/ https://other.com/'
    SERVICE2_URL = 'https://casclient2.com/service/'
    PGT_URL = 'https://casclient.con/pgt/'


    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(self.LOGIN,
                password=self.PASSWORD, email=self.EMAIL,
                first_name=self.FIRST_NAME, last_name=self.LAST_NAME)
        self.service = Service.objects.create(name=self.NAME, slug=self.SLUG,
                urls=self.URL, identifier_attribute='django_user_username',
                logout_url=self.URL + 'logout/')
        self.service_attribute1 = Attribute.objects.create(
                service=self.service,
                slug='email',
                attribute_name='django_user_email')
        self.service2 = Service.objects.create(name=self.NAME2,
                slug=self.SLUG2, urls=self.URL2,
                identifier_attribute='django_user_email')
        self.service2_attribute1 = Attribute.objects.create(
                service=self.service2,
                slug='username',
                attribute_name='django_user_username')
        self.factory = RequestFactory()

    def test_service_matching(self):
        self.service.clean()
        self.service2.clean()
        self.assertEqual(Service.objects.for_service(self.URL), self.service)
        for service in self.URL2.split():
            self.assertEqual(Service.objects.for_service(service), self.service2)
        self.assertEqual(Service.objects.for_service('http://google.com'), None)

    def test_login_failure(self):
        client = Client()
        response = client.get('/idp/cas/login/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('no service', response.content)
        response = client.get('/idp/cas/login/', {constants.SERVICE_PARAM: 'http://google.com/'})
        self.assertRedirectsComplex(response, 'http://google.com/')
        response = client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL,
            constants.RENEW_PARAM: '', constants.GATEWAY_PARAM: ''})
        self.assertRedirectsComplex(response, self.URL)
        response = client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL,
            constants.GATEWAY_PARAM: ''})
        self.assertRedirectsComplex(response, self.URL)

    def test_login_validate(self):
        response = self.client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 302)
        ticket = Ticket.objects.get()
        location = response['Location']
        url = location.split('?')[0]
        query = urlparse.parse_qs(location.split('?')[1])
        self.assertEquals(url, 'http://testserver/login/')
        self.assertIn('nonce', query)
        self.assertIn('next', query)
        self.assertEquals(query['nonce'], [ticket.ticket_id])
        next_url, next_url_query = query['next'][0].split('?')
        next_url_query = urlparse.parse_qs(next_url_query)
        self.assertEquals(next_url, '/idp/cas/continue/')
        self.assertEquals(set(next_url_query.keys()),
                set([constants.SERVICE_PARAM]))
        self.assertEquals(next_url_query[constants.SERVICE_PARAM], [self.URL])
        response = self.client.post(location, {'login-password-submit': '',
            'username': self.LOGIN, 'password': self.PASSWORD}, follow=False)
        self.assertIn(AUTHENTICATION_EVENTS_SESSION_KEY, self.client.session)
        self.assertIn('nonce', self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0])
        self.assertIn(ticket.ticket_id, self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0]['nonce'])
        self.assertRedirectsComplex(response, query['next'][0], nonce=ticket.ticket_id)
        response = self.client.get(response.url)
        self.assertRedirectsComplex(response, self.URL, ticket=ticket.ticket_id)
        # Check logout state has been updated
        ticket = Ticket.objects.get()
        self.assertIn(constants.SESSION_CAS_LOGOUTS, self.client.session)
        self.assertEquals(self.client.session[constants.SESSION_CAS_LOGOUTS],
                [[ticket.service.name, ticket.service.logout_url, ticket.service.logout_use_iframe,
                    ticket.service.logout_use_iframe_timeout]])
        # Do not the same client for direct calls from the CAS service provider
        # to prevent use of the user session
        client = Client()
        ticket_id = urlparse.parse_qs(response.url.split('?')[1])[constants.TICKET_PARAM][0]
        response = client.get('/idp/cas/validate/', {constants.TICKET_PARAM:
            ticket_id, constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response['content-type'], 'text/plain')
        self.assertEquals(response.content, 'yes\n%s\n' % self.LOGIN)
        # Verify ticket has been deleted
        with self.assertRaises(Ticket.DoesNotExist):
            Ticket.objects.get()

    def test_login_service_validate(self):
        response = self.client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 302)
        ticket = Ticket.objects.get()
        location = response['Location']
        url = location.split('?')[0]
        query = urlparse.parse_qs(location.split('?')[1])
        self.assertEquals(url, 'http://testserver/login/')
        self.assertIn('nonce', query)
        self.assertIn('next', query)
        self.assertEquals(query['nonce'], [ticket.ticket_id])
        next_url, next_url_query = query['next'][0].split('?')
        next_url_query = urlparse.parse_qs(next_url_query)
        self.assertEquals(next_url, '/idp/cas/continue/')
        self.assertEquals(set(next_url_query.keys()),
                set([constants.SERVICE_PARAM]))
        self.assertEquals(next_url_query[constants.SERVICE_PARAM], [self.URL])
        response = self.client.post(location, {'login-password-submit': '',
            'username': self.LOGIN, 'password': self.PASSWORD}, follow=False)
        self.assertIn(AUTHENTICATION_EVENTS_SESSION_KEY, self.client.session)
        self.assertIn('nonce', self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0])
        self.assertIn(ticket.ticket_id, self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0]['nonce'])
        self.assertRedirectsComplex(response, query['next'][0], nonce=ticket.ticket_id)
        response = self.client.get(response.url)
        self.assertRedirectsComplex(response, self.URL, ticket=ticket.ticket_id)
        # Check logout state has been updated
        ticket = Ticket.objects.get()
        self.assertIn(constants.SESSION_CAS_LOGOUTS, self.client.session)
        self.assertEquals(self.client.session[constants.SESSION_CAS_LOGOUTS],
                [[ticket.service.name, ticket.service.logout_url, ticket.service.logout_use_iframe,
                    ticket.service.logout_use_iframe_timeout]])
        # Do not the same client for direct calls from the CAS service provider
        # to prevent use of the user session
        client = Client()
        ticket_id = urlparse.parse_qs(response.url.split('?')[1])[constants.TICKET_PARAM][0]
        response = client.get('/idp/cas/serviceValidate/', {constants.TICKET_PARAM:
            ticket_id, constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response['content-type'], 'text/xml')
        EMAIL_ELT = '{%s}%s' % (constants.CAS_NAMESPACE, 'email')
        constraints = (
                ((constants.AUTHENTICATION_SUCCESS_ELT, constants.USER_ELT),
                    self.LOGIN, None),
                ((constants.AUTHENTICATION_SUCCESS_ELT,
                    constants.ATTRIBUTES_ELT, EMAIL_ELT), self.EMAIL, None),
        )
        self.assertEqualsXML(response, constraints)
        # Verify ticket has been deleted
        with self.assertRaises(Ticket.DoesNotExist):
            Ticket.objects.get()

    def test_login_service_validate_without_renew_failure(self):
        response = self.client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 302)
        ticket = Ticket.objects.get()
        location = response['Location']
        url = location.split('?')[0]
        query = urlparse.parse_qs(location.split('?')[1])
        self.assertEquals(url, 'http://testserver/login/')
        self.assertIn('nonce', query)
        self.assertIn('next', query)
        self.assertEquals(query['nonce'], [ticket.ticket_id])
        next_url, next_url_query = query['next'][0].split('?')
        next_url_query = urlparse.parse_qs(next_url_query)
        self.assertEquals(next_url, '/idp/cas/continue/')
        self.assertEquals(set(next_url_query.keys()),
                set([constants.SERVICE_PARAM]))
        self.assertEquals(next_url_query[constants.SERVICE_PARAM], [self.URL])
        response = self.client.post(location, {'login-password-submit': '',
            'username': self.LOGIN, 'password': self.PASSWORD}, follow=False)
        self.assertIn(AUTHENTICATION_EVENTS_SESSION_KEY, self.client.session)
        self.assertIn('nonce', self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0])
        self.assertIn(ticket.ticket_id, self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0]['nonce'])
        self.assertRedirectsComplex(response, query['next'][0], nonce=ticket.ticket_id)
        response = self.client.get(response.url)
        self.assertRedirectsComplex(response, self.URL, ticket=ticket.ticket_id)
        # Check logout state has been updated
        ticket = Ticket.objects.get()
        self.assertIn(constants.SESSION_CAS_LOGOUTS, self.client.session)
        self.assertEquals(self.client.session[constants.SESSION_CAS_LOGOUTS],
                [[ticket.service.name, ticket.service.logout_url, ticket.service.logout_use_iframe,
                    ticket.service.logout_use_iframe_timeout]])
        # Do not the same client for direct calls from the CAS service provider
        # to prevent use of the user session
        client = Client()
        ticket_id = urlparse.parse_qs(response.url.split('?')[1])[constants.TICKET_PARAM][0]
        response = client.get('/idp/cas/serviceValidate/', {constants.TICKET_PARAM:
            ticket_id, constants.SERVICE_PARAM: self.URL, constants.RENEW_PARAM: ''})
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response['content-type'], 'text/xml')
        constraints = (
                ((constants.AUTHENTICATION_FAILURE_ELT), None, {
                    constants.CODE_ATTR: constants.INVALID_TICKET_SPEC_ERROR}),
        )
        self.assertEqualsXML(response, constraints)
        # Verify ticket has been deleted
        with self.assertRaises(Ticket.DoesNotExist):
            Ticket.objects.get()

    def test_login_proxy_validate_on_service_ticket(self):
        response = self.client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 302)
        ticket = Ticket.objects.get()
        location = response['Location']
        url = location.split('?')[0]
        query = urlparse.parse_qs(location.split('?')[1])
        self.assertEquals(url, 'http://testserver/login/')
        self.assertIn('nonce', query)
        self.assertIn('next', query)
        self.assertEquals(query['nonce'], [ticket.ticket_id])
        next_url, next_url_query = query['next'][0].split('?')
        next_url_query = urlparse.parse_qs(next_url_query)
        self.assertEquals(next_url, '/idp/cas/continue/')
        self.assertEquals(set(next_url_query.keys()),
                set([constants.SERVICE_PARAM]))
        self.assertEquals(next_url_query[constants.SERVICE_PARAM], [self.URL])
        response = self.client.post(location, {'login-password-submit': '',
            'username': self.LOGIN, 'password': self.PASSWORD}, follow=False)
        self.assertIn(AUTHENTICATION_EVENTS_SESSION_KEY, self.client.session)
        self.assertIn('nonce', self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0])
        self.assertIn(ticket.ticket_id, self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0]['nonce'])
        self.assertRedirectsComplex(response, query['next'][0], nonce=ticket.ticket_id)
        response = self.client.get(response.url)
        self.assertRedirectsComplex(response, self.URL, ticket=ticket.ticket_id)
        # Check logout state has been updated
        ticket = Ticket.objects.get()
        self.assertIn(constants.SESSION_CAS_LOGOUTS, self.client.session)
        self.assertEquals(self.client.session[constants.SESSION_CAS_LOGOUTS],
                [[ticket.service.name, ticket.service.logout_url, ticket.service.logout_use_iframe,
                    ticket.service.logout_use_iframe_timeout]])
        # Do not the same client for direct calls from the CAS service provider
        # to prevent use of the user session
        client = Client()
        ticket_id = urlparse.parse_qs(response.url.split('?')[1])[constants.TICKET_PARAM][0]
        response = client.get('/idp/cas/proxyValidate/', {constants.TICKET_PARAM:
            ticket_id, constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response['content-type'], 'text/xml')
        EMAIL_ELT = '{%s}%s' % (constants.CAS_NAMESPACE, 'email')
        constraints = (
                ((constants.AUTHENTICATION_SUCCESS_ELT, constants.USER_ELT),
                    self.LOGIN, None),
                ((constants.AUTHENTICATION_SUCCESS_ELT,
                    constants.ATTRIBUTES_ELT, EMAIL_ELT), self.EMAIL, None),
        )
        self.assertEqualsXML(response, constraints)
        # Verify ticket has been deleted
        with self.assertRaises(Ticket.DoesNotExist):
            Ticket.objects.get()

    @override_settings(A2_IDP_CAS_CHECK_PGT_URL=False)
    def test_proxy(self):
        response = self.client.get('/idp/cas/login/', {constants.SERVICE_PARAM: self.URL})
        self.assertEquals(response.status_code, 302)
        ticket = Ticket.objects.get()
        location = response['Location']
        url = location.split('?')[0]
        query = urlparse.parse_qs(location.split('?')[1])
        self.assertEquals(url, 'http://testserver/login/')
        self.assertIn('nonce', query)
        self.assertIn('next', query)
        self.assertEquals(query['nonce'], [ticket.ticket_id])
        next_url, next_url_query = query['next'][0].split('?')
        next_url_query = urlparse.parse_qs(next_url_query)
        self.assertEquals(next_url, '/idp/cas/continue/')
        self.assertEquals(set(next_url_query.keys()),
                set([constants.SERVICE_PARAM]))
        self.assertEquals(next_url_query[constants.SERVICE_PARAM], [self.URL])
        response = self.client.post(location, {'login-password-submit': '',
            'username': self.LOGIN, 'password': self.PASSWORD}, follow=False)
        self.assertIn(AUTHENTICATION_EVENTS_SESSION_KEY, self.client.session)
        self.assertIn('nonce', self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0])
        self.assertIn(ticket.ticket_id, self.client.session[AUTHENTICATION_EVENTS_SESSION_KEY][0]['nonce'])
        self.assertRedirectsComplex(response, query['next'][0], nonce=ticket.ticket_id)
        response = self.client.get(response.url)
        self.assertRedirectsComplex(response, self.URL, ticket=ticket.ticket_id)
        # Check logout state has been updated
        ticket = Ticket.objects.get()
        self.assertIn(constants.SESSION_CAS_LOGOUTS, self.client.session)
        self.assertEquals(self.client.session[constants.SESSION_CAS_LOGOUTS],
                [[ticket.service.name, ticket.service.logout_url, ticket.service.logout_use_iframe,
                    ticket.service.logout_use_iframe_timeout]])
        # Do not the same client for direct calls from the CAS service provider
        # to prevent use of the user session
        client = Client()
        ticket_id = urlparse.parse_qs(response.url.split('?')[1])[constants.TICKET_PARAM][0]
        response = client.get('/idp/cas/serviceValidate/', {constants.TICKET_PARAM:
            ticket_id, constants.SERVICE_PARAM: self.URL, constants.PGT_URL_PARAM: self.PGT_URL})
        for key in client.session.iterkeys():
            if key.startswith(constants.PGT_IOU_PREFIX):
                pgt_iou = key
                pgt = client.session[key]
                break
        else:
            self.assertTrue(False, 'PGTIOU- not found in session')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response['content-type'], 'text/xml')
        constraints = (
                 ((constants.AUTHENTICATION_SUCCESS_ELT, constants.USER_ELT), self.LOGIN, None),
                 ((constants.AUTHENTICATION_SUCCESS_ELT, constants.PGT_ELT), pgt_iou, None),
        )
        self.assertEqualsXML(response, constraints)
        # Verify service ticket has been deleted
        with self.assertRaises(Ticket.DoesNotExist):
            Ticket.objects.get(ticket_id=ticket_id)
        # Verify pgt ticket exists
        pgt_ticket = Ticket.objects.get(ticket_id=pgt)
        self.assertEquals(pgt_ticket.user, self.user)
        self.assertIsNone(pgt_ticket.expire)
        self.assertEquals(pgt_ticket.service, self.service)
        self.assertEquals(pgt_ticket.service_url, self.URL)
        self.assertEquals(pgt_ticket.proxies, self.PGT_URL)
        # Try to get a proxy ticket for service 2
        # it should fail since no proxy authorization exists
        client = Client()
        response = client.get('/idp/cas/proxy/', {
            constants.PGT_PARAM: pgt,
            constants.TARGET_SERVICE_PARAM: self.SERVICE2_URL
        })
        constraints = (
                 ((constants.PROXY_FAILURE_ELT,), None, {
                     constants.CODE_ATTR: constants.PROXY_UNAUTHORIZED_ERROR
                  }),
        )
        self.assertEqualsXML(response, constraints)
        # Set proxy authorization
        self.service2.proxy.add(self.service)
        # Try again !
        response = client.get('/idp/cas/proxy/', {
            constants.PGT_PARAM: pgt,
            constants.TARGET_SERVICE_PARAM: self.SERVICE2_URL
        })
        pt = Ticket.objects.get(ticket_id__startswith=constants.PT_PREFIX)
        self.assertEquals(pt.user, self.user)
        self.assertIsNotNone(pt.expire)
        self.assertEquals(pt.service, self.service2)
        self.assertEquals(pt.service_url, self.SERVICE2_URL)
        self.assertEquals(pt.proxies, self.PGT_URL)
        constraints = (
                 ((constants.PROXY_SUCCESS_ELT, constants.PROXY_TICKET_ELT), pt.ticket_id, None),
        )
        self.assertEqualsXML(response, constraints)
        # Now service2 try to resolve the proxy ticket
        client = Client()
        response = client.get('/idp/cas/proxyValidate/', {
            constants.TICKET_PARAM: pt.ticket_id,
            constants.SERVICE_PARAM: self.SERVICE2_URL})
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response['content-type'], 'text/xml')
        USERNAME_ELT = '{%s}%s' % (constants.CAS_NAMESPACE, 'username')
        constraints = (
                ((constants.AUTHENTICATION_SUCCESS_ELT, constants.USER_ELT),
                    self.EMAIL, None),
                ((constants.AUTHENTICATION_SUCCESS_ELT,
                    constants.ATTRIBUTES_ELT, USERNAME_ELT), self.LOGIN, None),
        )
        self.assertEqualsXML(response, constraints)
        # Verify ticket has been deleted
        with self.assertRaises(Ticket.DoesNotExist):
            Ticket.objects.get(ticket_id=pt.ticket_id)
        # Check invalidation of PGT when session is closed
        self.client.logout()
        response = client.get('/idp/cas/proxy/', {
            constants.PGT_PARAM: pgt,
            constants.TARGET_SERVICE_PARAM: self.SERVICE2_URL
        })
        constraints = (
                 ((constants.PROXY_FAILURE_ELT,), 'session has expired', {
                     constants.CODE_ATTR: constants.BAD_PGT_ERROR,
                  }),
        )
        self.assertEqualsXML(response, constraints)