.. _settings_listing:

============
All settings
============

Activate or deactivate debug mode
=================================

Variable: DEBUG

Values:

* False: deactivate debug mode
* True: activate debug mode

Manage session cookie duration
==============================

Variable: SESSION_EXPIRE_AT_BROWSER_CLOSE

Values:

* False: Cookies are not removed when browser is closed.
* True: Cookies are removed when browser is closed.

Variable: SESSION_COOKIE_AGE

Value:

* Seconds (36000 equal 10 hours)

Time zone selection
===================

Variable: TIME_ZONE

Values:

* See http://en.wikipedia.org/wiki/List_of_tz_zones_by_name

Activate or deactivate SSL authentication
=========================================

Variable: AUTH_SSL

Values:

* False: deactivate SSL authentication
* True: activate SSL authentication

Activate or deactivate OpenID authentication, Authentic 2 is an OpenID relying party
====================================================================================

Variable: AUTH_OPENID

Values:

* False: deactivate OpenID authentication
* True: activate OpenID authentication

Activate or deactivate Authentic 2 as a SAML2 identity provider
===============================================================

Variable: IDP_SAML2

Values:

* False: deactivate SAML2 identity provider
* True: activate SAML2 identity provider

Configure SAML2 keys
====================

* SAML_SIGNATURE_PUBLIC_KEY: Certtificate or public key for signature
* SAML_SIGNATURE_PRIVATE_KEY: Private key for signature
* SAML_ENCRYPTION_PUBLIC_KEY: Certtificate or public key for encryption
* SAML_ENCRYPTION_PRIVATE_KEY: Private key for encryption

Values are pem files of X509 certificate or key, e.g.:
SAML_SIGNATURE_PRIVATE_KEY = '''-----BEGIN RSA PRIVATE KEY-----
MII...WA==
-----END RSA PRIVATE KEY-----'''

If SAML_ENCRYPTION_PUBLIC_KEY or SAML_ENCRYPTION_PRIVATE_KEY are not given,
the signature keys are used for encryption.


Activate or deactivate Authentic 2 as a CAS server
==================================================

Variable: IDP_CAS

Values:

* False: deactivate CAS server
* True: activate CAS server
