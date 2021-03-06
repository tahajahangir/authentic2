import urlparse
import os.path
import urllib
import httplib
import logging
import re
import datetime

import requests

from authentic2.compat_lasso import lasso
from django.conf import settings
from django.http import HttpResponseRedirect, Http404, HttpResponse
from django.shortcuts import render
from django.core.exceptions import ValidationError

from authentic2.saml.models import (LibertyFederation, LibertyProvider,
                                    LibertyServiceProvider, SPOptionsIdPPolicy)
from authentic2.saml import models
from authentic2.saml import saml2utils

from authentic2.http_utils import get_url
from authentic2.decorators import RequestCache
from authentic2.idp.saml import app_settings
from .. import nonce

AUTHENTIC_STATUS_CODE_NS = "http://authentic.entrouvert.org/status_code/"
AUTHENTIC_SAME_ID_SENTINEL = \
    'urn:authentic.entrouvert.org:same-as-provider-entity-id'
AUTHENTIC_STATUS_CODE_UNKNOWN_PROVIDER = AUTHENTIC_STATUS_CODE_NS + \
    "UnknownProvider"
AUTHENTIC_STATUS_CODE_MISSING_NAMEID = AUTHENTIC_STATUS_CODE_NS + \
    "MissingNameID"
AUTHENTIC_STATUS_CODE_MISSING_SESSION_INDEX = AUTHENTIC_STATUS_CODE_NS + \
    "MissingSessionIndex"
AUTHENTIC_STATUS_CODE_UNKNOWN_SESSION = AUTHENTIC_STATUS_CODE_NS + \
    "UnknownSession"
AUTHENTIC_STATUS_CODE_MISSING_DESTINATION = AUTHENTIC_STATUS_CODE_NS + \
    "MissingDestination"
AUTHENTIC_STATUS_CODE_INTERNAL_SERVER_ERROR = AUTHENTIC_STATUS_CODE_NS + \
    "InternalServerError"
AUTHENTIC_STATUS_CODE_UNAUTHORIZED = AUTHENTIC_STATUS_CODE_NS + \
    "Unauthorized"

logger = logging.getLogger(__name__)

# timeout for messages and assertions issue instant
NONCE_TIMEOUT = getattr(
    settings, 'SAML2_NONCE_TIMEOUT', getattr(settings, 'NONCE_TIMEOUT', 30))
# do we check id on SAML2 messages ?
CHECKS_ID = getattr(settings, 'SAML2_CHECKS_ID', True)


def get_soap_message(request):
    '''Verify that POST content looks like a SOAP message and returns it'''
    assert request.method == 'POST' \
        and 'CONTENT_TYPE' in request.META \
        and 'text/xml' in request.META['CONTENT_TYPE'], 'not a SOAP message'
    return request.body


def get_http_binding(request):
    if request.method in ('GET', 'HEAD'):
        return 'GET'
    elif request.method == 'POST':
        # disambiguate SOAP and form POST
        if request.META.get('CONTENT_TYPE') in ['application/x-www-form-urlencoded',
                                                'multipart/form-data']:
            return 'POST'
        else:
            return 'SOAP'

# SAMLv2 methods


def get_base_path(request, metadata):
    '''Get endpoints base path given metadata path
    '''
    path = urlparse.urlparse(metadata).path
    return request.build_absolute_uri(os.path.dirname(path))


def get_entity_id(request, metadata):
    '''Return the EntityID, given metadata absolute path
    '''
    return request.build_absolute_uri(metadata)

asynchronous_bindings = [lasso.SAML2_METADATA_BINDING_REDIRECT,
                         lasso.SAML2_METADATA_BINDING_POST]
soap_bindings = [lasso.SAML2_METADATA_BINDING_SOAP]
all_bindings = asynchronous_bindings + [lasso.SAML2_METADATA_BINDING_SOAP]


def get_saml2_metadata(request, metadata, idp_map=None, sp_map=None,
                       options={}):
    metagen = saml2utils.Saml2Metadata(get_entity_id(request, metadata),
                                       url_prefix=get_base_path(request,
                                                                metadata))
    if idp_map:
        metagen.add_idp_descriptor(idp_map, options)
    if sp_map:
        metagen.add_sp_descriptor(sp_map, options)
    return str(metagen)


def create_saml2_server(request, metadata, idp_map=None, sp_map=None,
                        options={}):
    '''Create a lasso Server object for using with a profile'''
    if app_settings.ADD_CERTIFICATE_TO_KEY_INFO:
        certificate_content = options.get('key')
    else:
        certificate_content = None
    server = lasso.Server.newFromBuffers(
        get_saml2_metadata(request, metadata, idp_map=idp_map, sp_map=sp_map,
                           options=options),
        options.get('private_key'), certificate_content=certificate_content)
    if not server:
        raise Exception('Cannot create LassoServer object')
    return server


def get_saml2_post_response(request):
    '''Extract the SAMLRequest field from the POST'''
    msg = request.POST.get(lasso.SAML2_FIELD_RESPONSE, '')
    assert msg is not None, 'no message received'
    logger.debug('%s: %s', lasso.SAML2_FIELD_RESPONSE, msg)
    return msg


def get_saml2_post_request(request):
    '''Extract the SAMLRequest field from the POST'''
    return request.POST.get(lasso.SAML2_FIELD_REQUEST, '')


def get_saml2_query_request(request):
    return request.META.get('QUERY_STRING', '')


def get_saml2_soap_request(request):
    return get_soap_message(request)


def get_saml2_request_message_async_binding(request):
    '''Return SAMLv2 message whatever the HTTP binding used'''
    binding = get_http_binding(request)
    if binding == 'GET':
        return get_saml2_query_request(request)
    elif binding == 'POST':
        return get_saml2_post_request(request)
    else:
        raise Http404('This endpoint is only for asynchornous bindings')


def get_saml2_request_message(request):
    '''Return SAMLv2 message whatever the HTTP binding used'''
    binding = get_http_binding(request)
    if binding == 'GET':
        msg = get_saml2_query_request(request)
    elif binding == 'POST':
        msg = get_saml2_post_request(request)
    elif binding == 'SOAP':
        msg = get_saml2_soap_request(request)
    else:
        msg = None
    assert msg, 'no saml2 request message found'
    return msg


def return_saml2_response(request, profile, title=''):
    '''Finish your SAMLv2 views with this method to return a SAML
    response'''
    return return_saml2(request, profile, lasso.SAML2_FIELD_RESPONSE, title)


def return_saml2_request(request, profile, title=''):
    '''Finish your SAMLv2 views with this method to return a SAML
    request'''
    return return_saml2(request, profile, lasso.SAML2_FIELD_REQUEST, title)


def return_saml2(request, profile, field_name, title=''):
    '''Helper to handle SAMLv2 bindings to emit request and responses'''
    logger.debug('profile.msgBody: %r', profile.msgBody)
    logger.debug('profile.msgUrl: %r', profile.msgUrl)
    logger.debug('profile.msgRelayState: %r', profile.msgRelayState)
    logger.debug('field_name: %s', field_name)
    if profile.msgBody:
        if profile.msgUrl:
            return render(
                request,
                'saml/post_form.html',
                {
                    'title': title,
                    'url': profile.msgUrl,
                    'fieldname': field_name,
                    'body': profile.msgBody,
                    'relay_state': profile.msgRelayState
                })
        return HttpResponse(profile.msgBody, content_type='text/xml')
    elif profile.msgUrl:
        return HttpResponseRedirect(profile.msgUrl)
    else:
        raise TypeError('profile do not contain a response')


def check_id_and_issue_instant(request_response_or_assertion, now=None):
    '''
       Check that issue instant is not older than a timeout and also checks
       that the id has never been seen before.

       Nonce are cached for two times the relative timeout length of the issue
       instant.
    '''
    if now is None:
        now = datetime.datetime.utcnow()
    try:
        issue_instant = request_response_or_assertion.issueInstant
        issue_instant = saml2utils.iso8601_to_datetime(issue_instant)
        delta = datetime.timedelta(seconds=NONCE_TIMEOUT)
        if not (now - delta <= issue_instant < now + delta):
            logger.warning('IssueInstant %s not in the interval [%s, %s[',
                           issue_instant, now-delta, now+delta)
            return False
    except ValueError:
        logger.error('Unable to parse an IssueInstant: %r', issue_instant)
        return False
    if CHECKS_ID:
        _id = request_response_or_assertion.id
        if _id is None:
            logger.warning('missing ID')
            return False
        if not nonce.accept_nonce(_id, 'SAML', 2*NONCE_TIMEOUT):
            logger.warning("ID '%r' already used, request/response/assertion "
                           "refused", _id)
            return False
    return True


def return_saml_soap_response(profile):
    return HttpResponse(profile.msgBody, content_type='text/xml')

# Helper method to handle profiles endpoints
# In the future we should move away from monolithic object (LassoIdentity and
# LassoSession) holding all the datas, to manipulate them at row Level with
# LibertyFederation objects.

START_IDENTITY_DUMP = '''<Identity xmlns="http://www.entrouvert.org/namespaces/lasso/0.0" \
Version="2">
'''
MIDDLE_IDENTITY_DUMP = '''<lasso:Federation \
xmlns:lasso="http://www.entrouvert.org/namespaces/lasso/0.0" \
xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" \
RemoteProviderID="{sp_id}" FederationDumpVersion="2">
    <lasso:LocalNameIdentifier>
        <saml:NameID Format="{format}" {qualifiers}>{content}</saml:NameID>
    </lasso:LocalNameIdentifier>
</lasso:Federation>
'''
END_IDENTITY_DUMP = '''</Identity>'''


def federations_to_identity_dump(self_entity_id, federations):
    l = [START_IDENTITY_DUMP]
    for federation in federations:
        name_id_qualifier = federation.name_id_qualifier
        name_id_sp_name_qualifier = federation.name_id_sp_name_qualifier
        # ease migration of federations by making qualifiers relative to the
        # linked idp or sp
        if federation.sp:
            sp_id = federation.sp.liberty_provider.entity_id
            if name_id_sp_name_qualifier == AUTHENTIC_SAME_ID_SENTINEL:
                name_id_sp_name_qualifier = sp_id
            if name_id_qualifier == AUTHENTIC_SAME_ID_SENTINEL:
                name_id_qualifier = self_entity_id
        elif federation.idp:
            sp_id = self_entity_id
            if name_id_sp_name_qualifier == AUTHENTIC_SAME_ID_SENTINEL:
                name_id_sp_name_qualifier = self_entity_id
            if name_id_qualifier == AUTHENTIC_SAME_ID_SENTINEL:
                name_id_qualifier = federation.idp.liberty_provider.entity_id
        qualifiers = []
        if federation.name_id_qualifier:
            qualifiers.append(
                'NameQualifier="%s"' % name_id_qualifier)
        if federation.name_id_sp_name_qualifier:
            qualifiers.append(
                'SPNameQualifier="%s"' % name_id_sp_name_qualifier)
        l.append(MIDDLE_IDENTITY_DUMP.format(
            content=federation.name_id_content,
            format=federation.name_id_format,
            sp_id=sp_id,
            qualifiers=' '.join(qualifiers)))
    l.append(END_IDENTITY_DUMP)
    return ''.join(l)


def load_federation(request, entity_id, login, user=None):
    '''Load an identity dump from the database'''
    if not user:
        user = request.user
    assert user is not None

    identity_dump = federations_to_identity_dump(
        entity_id, LibertyFederation.objects.filter(user=user))
    login.setIdentityFromDump(identity_dump)


def retrieve_metadata_and_create(request, provider_id, sp_or_idp):
    logger.debug('trying to load %s from wkl', provider_id)
    if not provider_id.startswith('http'):
        logger.debug('not an http url, failing')
        return None
    # Try the WKL
    try:
        metadata = get_url(provider_id)
    except Exception, e:
        logging.error('SAML metadata autoload: failure to retrieve metadata '
                      'for entity id %s: %s', provider_id, e)
        return None
    logger.debug('loaded %d bytes', len(metadata))
    try:
        metadata = unicode(metadata, 'utf8')
    except:
        logging.error('SAML metadata autoload: retrieved metadata for entity '
                      'id %s is not UTF-8', provider_id)
        return None
    p = LibertyProvider(metadata=metadata)
    try:
        p.full_clean(exclude=['entity_id', 'protocol_conformance'])
    except ValidationError, e:
        logging.error('SAML metadata autoload: retrieved metadata for entity '
                      'id %s are invalid, %s', provider_id, e.args)
        return None
    except:
        logging.exception('SAML metadata autoload: retrieved metadata '
                          'validation raised an unknown exception')
        return None
    p.save()
    logger.debug('%s saved', p)
    s = LibertyServiceProvider(liberty_provider=p, enabled=True)
    s.save()
    return p


def load_provider(request, entity_id, server=None, sp_or_idp='sp',
                  autoload=False):
    '''Look up a provider in the database, and verify it handles wanted
       role be it sp or idp.

       Arguments:
       request -- the currently handled request
       entity_id -- the entity ID of the searched provider

       Keyword arguments:
       server -- a lasso.Server object into which to load the given provider
       sp_or_idp -- kind of the provider we are looking for, can be 'sp' or
       'idp', default to 'sp'
    '''
    try:
        liberty_provider = LibertyProvider.objects.get(entity_id=entity_id)
    except LibertyProvider.DoesNotExist:
        autoload = getattr(settings, 'SAML_METADATA_AUTOLOAD', 'none')
        if autoload and (autoload == 'sp' or autoload == 'both'):
            liberty_provider = retrieve_metadata_and_create(request, entity_id,
                                                            sp_or_idp)
            if not liberty_provider:
                return False
        else:
            return False
    try:
        service_provider = liberty_provider.service_provider
    except LibertyServiceProvider.DoesNotExist:
        return False
    if not service_provider.enabled:
        return False
    if server:
        server.addProviderFromBuffer(lasso.PROVIDER_ROLE_SP,
                                     liberty_provider.metadata.encode('utf8'))
        policy = get_sp_options_policy(liberty_provider)
        if policy:
            encryption_mode = 0
            if policy.encrypt_assertion:
                encryption_mode = lasso.ENCRYPTION_MODE_ASSERTION
            if policy.encrypt_nameid:
                encryption_mode = lasso.ENCRYPTION_MODE_NAMEID
            server.providers[entity_id].setEncryptionMode(encryption_mode)
    logger.debug('loaded provider %s', entity_id)
    return liberty_provider


# Federation management


def add_federation(user, login=None, name_id=None, provider_id=None):
    assert name_id or (login and login.nameIdentifier), \
        'missing name identifier'
    name_id = name_id or login.nameIdentifier
    kwargs = models.nameid2kwargs(name_id)
    if provider_id:
        kwargs['idp'] = LibertyProvider.objects.get(entity_id=provider_id) \
            .identity_provider
    fed = LibertyFederation(user=user, **kwargs)
    fed.save()
    logger.debug('federation %s linked to user %s', fed.name_id_content, user)
    return fed


def lookup_federation_by_name_identifier(name_id=None, profile=None):
    '''Try to find a LibertyFederation object for the given NameID or
       profile object.'''
    if not name_id:
        name_id = profile.nameIdentifier
    kwargs = models.nameid2kwargs(name_id)
    try:
        return LibertyFederation.objects.get(**kwargs)
    except:
        return None


def lookup_federation_by_name_id_and_provider_id(name_id, provider_id):
    '''Try to find a LibertyFederation object for the given NameID and
       the provider id.'''
    kwargs = models.nameid2kwargs(name_id)
    kwargs['idp'] = LibertyProvider.objects.get(entity_id=provider_id) \
        .identity_provider
    try:
        return LibertyFederation.objects.get(user__isnull=False, **kwargs)
    except:
        return None


# TODO: Does it happen that a user have multiple federation with a same idp? NO
def lookup_federation_by_user(user, qualifier):
    if not user or not qualifier:
        return None
    fed = LibertyFederation.objects.filter(user=user,
                                           name_id_qualifier=qualifier)
    if fed and fed.count() > 1:
        # TODO: delete all but the last record
        raise Exception('Unconsistent federation record for %s' % qualifier)
    if not fed:
        return None
    return fed[0]


class SOAPException(Exception):
    pass


def soap_call(url, msg):
    logger = logging.getLogger(__name__)
    try:
        logger.debug('SOAP call to %r with data %r', url, msg[:10000])
        response = requests.post(url, data=msg, headers={'Content-Type': 'text/xml'})
        response.raise_for_status()
    except requests.RequestException, e:
        logging.error('SOAP call to %r error %s with data %r', url, e, msg[:10000])
        raise SOAPException(url, e)
    logger.debug('SOAP call response %r', response.content[:10000])
    return response.content


def send_soap_request(request, profile):
    '''Send the SOAP request hold by the profile'''
    if not profile.msgUrl or not profile.msgBody:
        raise SOAPException('Missing body or url')
    return soap_call(profile.msgUrl, profile.msgBody, None)


def set_saml2_response_responder_status_code(response, code, msg=None):
    response.status = lasso.Samlp2Status()
    if msg:
        response.status.statusMessage = msg
    response.status.statusCode = lasso.Samlp2StatusCode()
    response.status.statusCode.value = lasso.SAML2_STATUS_CODE_RESPONDER
    response.status.statusCode.statusCode = lasso.Samlp2StatusCode()
    response.status.statusCode.statusCode.value = code

__root_refererer_re = re.compile('^(https?://[^/]*/?)')


def error_page(request, message, back=None, logger=None, warning=False):
    '''View that show a simple error page to the user with a back link.

         back - url for the back link, if None, return to root of the referer
                or the local root.
    '''
    if not logger:
        logger = logging
    if warning:
        logging.warning('Showing message %r on an error page' % message)
    else:
        logging.error('Showing message %r on an error page' % message)
    if back is None:
        referer = request.META.get('HTTP_REFERER')
        if referer:
            root_referer = __root_refererer_re.match(referer)
            if root_referer:
                back = root_referer.group(1)
        if back is None:
            back = '/'
    redirection_timeout = getattr(settings, 'REDIRECTION_TIMEOUT_AFTER_ERROR',
                                  2000)
    return render(request, 'error.html',
                  {
                      'msg': message,
                      'back': back,
                      'redir_timeout': redirection_timeout
                  })


def redirect_next(request, next):
    if next:
        return HttpResponseRedirect(next)
    else:
        return None


def soap_fault(request, faultcode='soap:Client', faultstring=None):
    if faultstring:
        faultstring = '\n        <faultstring>%s</faultstring>\n' % faultstring
    content = '''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body><soap:Fault>
       <faultcode>%(faultcode)s</faultcode>%(faultstring)s
    </soap:Fault></soap:Body>
</soap:Envelope>''' % locals()
    return HttpResponse(content, content_type="text/xml")


@RequestCache
def get_sp_options_policy_all():
    try:
        return SPOptionsIdPPolicy.objects.get(name='All', enabled=True)
    except SPOptionsIdPPolicy.DoesNotExist:
        pass


@RequestCache
def get_sp_options_policy_default():
    try:
        return SPOptionsIdPPolicy.objects.get(name='Default', enabled=True)
    except SPOptionsIdPPolicy.DoesNotExist:
        pass


def get_sp_options_policy(provider):
    policy = get_sp_options_policy_all()
    if policy:
        return policy
    if provider.service_provider.enable_following_sp_options_policy:
        policy = provider.service_provider.sp_options_policy
        if policy and policy.enabled:
            return provider.service_provider.sp_options_policy
    return get_sp_options_policy_default()


def get_session_not_on_or_after(assertion):
    '''Extract the minimal value for the SessionNotOnOrAfter found in the given
       assertion AuthenticationStatement(s).
    '''
    session_not_on_or_afters = []
    if hasattr(assertion, 'authnStatement'):
        for authn_statement in assertion.authnStatement:
            if authn_statement.sessionNotOnOrAfter:
                value = authn_statement.sessionNotOnOrAfter
                try:
                    session_not_on_or_afters.append(
                        saml2utils.iso8601_to_datetime(value))
                except ValueError:
                    logging.getLogger(__name__).error(
                        'unable to parse SessionNotOnOrAfter value %s, will '
                        'use default value for session length.', value)
    if session_not_on_or_afters:
        return reduce(min, session_not_on_or_afters)
    return None
