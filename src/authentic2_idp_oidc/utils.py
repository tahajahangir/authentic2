import json
import hashlib
import urlparse
import base64
import uuid

from jwcrypto.jwk import JWK, JWKSet, InvalidJWKValue
from jwcrypto.jwt import JWT

from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.utils.encoding import smart_bytes

from authentic2 import hooks, crypto
from authentic2.attributes_ng.engine import get_attributes

from . import app_settings


def base64url(content):
    return base64.urlsafe_b64encode(content).strip('=')


def get_jwkset():
    try:
        jwkset = json.dumps(app_settings.JWKSET)
    except Exception as e:
        raise ImproperlyConfigured('invalid setting A2_IDP_OIDC_JWKSET: %s' % e)
    try:
        jwkset = JWKSet.from_json(jwkset)
    except InvalidJWKValue as e:
        raise ImproperlyConfigured('invalid setting A2_IDP_OIDC_JWKSET: %s' % e)
    if len(jwkset['keys']) < 1:
        raise ImproperlyConfigured('empty A2_IDP_OIDC_JWKSET')
    return jwkset


def get_first_rsa_sig_key():
    for key in get_jwkset()['keys']:
        if key._params['kty'] != 'RSA':
            continue
        use = key._params.get('use')
        if use is None or use == 'sig':
            return key
    return None


def make_idtoken(client, claims):
    '''Make a serialized JWT targeted for this client'''
    if client.idtoken_algo == client.ALGO_HMAC:
        header = {'alg': 'HS256'}
        jwk = JWK(kty='oct', k=base64url(client.client_secret.encode('utf-8')))
    elif client.idtoken_algo == client.ALGO_RSA:
        header = {'alg': 'RS256'}
        jwk = get_first_rsa_sig_key()
        header['kid'] = jwk.key_id
        if jwk is None:
            raise ImproperlyConfigured('no RSA key for signature operation in A2_IDP_OIDC_JWKSET')
    else:
        raise NotImplementedError
    jwt = JWT(header=header, claims=claims)
    jwt.make_signed_token(jwk)
    return jwt.serialize()


def scope_set(data):
    '''Convert a scope string into a set of scopes'''
    return set([scope.strip() for scope in data.split()])


def clean_words(data):
    '''Clean and order a list of words'''
    return u' '.join(sorted(map(unicode.strip, data.split())))


def url_domain(url):
    return urlparse.urlparse(url).netloc.split(':')[0]


def make_sub(client, user):
    if client.identifier_policy in (client.POLICY_PAIRWISE, client.POLICY_PAIRWISE_REVERSIBLE):
        return make_pairwise_sub(client, user)
    elif client.identifier_policy == client.POLICY_UUID:
        return unicode(user.uuid)
    elif client.identifier_policy == client.POLICY_EMAIL:
        return user.email
    else:
        raise NotImplementedError


def make_pairwise_sub(client, user):
    '''Make a pairwise sub'''
    if client.identifier_policy == client.POLICY_PAIRWISE:
        return make_pairwise_unreversible_sub(client, user)
    elif client.identifier_policy == client.POLICY_PAIRWISE_REVERSIBLE:
        return make_pairwise_reversible_sub(client, user)
    else:
        raise NotImplementedError(
            'unknown pairwise client.identifier_policy %s' % client.identifier_policy)


def get_sector_identifier(client):
    if client.authorization_mode in (client.AUTHORIZATION_MODE_BY_SERVICE,
                                     client.AUTHORIZATION_MODE_NONE):
        sector_identifier = None
        if client.sector_identifier_uri:
            sector_identifier = url_domain(client.sector_identifier_uri)
        else:
            for redirect_uri in client.redirect_uris.split():
                hostname = url_domain(redirect_uri)
                if sector_identifier is None:
                    sector_identifier = hostname
                elif sector_identifier != hostname:
                    raise ImproperlyConfigured('all redirect_uri do not have the same hostname')
    elif client.authorization_mode == client.AUTHORIZATION_MODE_BY_OU:
        sector_identifier = client.ou.slug
    else:
        raise NotImplementedError(
            'unknown client.authorization_mode %s' % client.authorization_mode)
    return sector_identifier


def make_pairwise_unreversible_sub(client, user):
    sector_identifier = get_sector_identifier(client)
    sub = sector_identifier + str(user.uuid) + settings.SECRET_KEY
    sub = base64.b64encode(hashlib.sha256(sub).digest())
    return sub


def make_pairwise_reversible_sub(client, user):
    return make_pairwise_reversible_sub_from_uuid(client, user.uuid)


def make_pairwise_reversible_sub_from_uuid(client, user_uuid):
    try:
        identifier = uuid.UUID(user_uuid).bytes
    except ValueError:
        return None
    sector_identifier = get_sector_identifier(client)
    return crypto.aes_base64url_deterministic_encrypt(
        settings.SECRET_KEY, identifier, sector_identifier)


def reverse_pairwise_sub(client, sub):
    sector_identifier = get_sector_identifier(client)
    try:
        return crypto.aes_base64url_deterministic_decrypt(
            settings.SECRET_KEY, sub, sector_identifier)
    except crypto.DecryptionError:
        return None


def normalize_claim_values(values):
    values_list = []
    if isinstance(values, basestring) or not hasattr(values, '__iter__'):
        return values
    for value in values:
        if isinstance(value, bool):
            value = str(value).lower()
        values_list.append(value)
    return values_list


def create_user_info(client, user, scope_set, id_token=False):
    '''Create user info dictionnary'''
    user_info = {
        'sub': make_sub(client, user)
    }
    attributes = get_attributes({
        'user': user, 'request': None, 'service': client,
        '__wanted_attributes': client.get_wanted_attributes()})
    for claim in client.oidcclaim_set.filter(name__isnull=False):
        if not set(claim.get_scopes()).intersection(scope_set):
            continue
        user_info[claim.name] = normalize_claim_values(attributes[claim.value])
        # check if attribute is verified
        if claim.value + ':verified' in attributes:
            user_info[claim.value + '_verified'] = True
    hooks.call_hooks('idp_oidc_modify_user_info', client, user, scope_set, user_info)
    return user_info


def get_issuer(request):
    return request.build_absolute_uri('/')


def get_session_id(request, client):
    '''Derive an OIDC Session Id from the real session identifier, the sector
       identifier of the RP and the secret key of the Django instance'''
    session_key = smart_bytes(request.session.session_key)
    sector_identifier = smart_bytes(get_sector_identifier(client))
    secret_key = smart_bytes(settings.SECRET_KEY)
    return hashlib.md5(session_key + sector_identifier + secret_key).hexdigest()


def get_oidc_sessions(request):
    return request.session.get('oidc_sessions', {})


def add_oidc_session(request, client):
    oidc_sessions = request.session.setdefault('oidc_sessions', {})
    if not client.frontchannel_logout_uri:
        return
    uri = client.frontchannel_logout_uri
    oidc_session = {
        'frontchannel_logout_uri': uri,
        'frontchannel_timeout': client.frontchannel_timeout,
        'name': client.name,
        'sid': get_session_id(request, client),
        'iss': get_issuer(request),
    }
    if oidc_sessions.get(uri) == oidc_session:
        # already present
        return
    oidc_sessions[uri] = oidc_session
    # force session save
    request.session.modified = True
