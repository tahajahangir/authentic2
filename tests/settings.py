import os

# use a faster hasing scheme for passwords
if 'PASSWORD_HASHERS' not in locals():
    from django.conf.global_settings import PASSWORD_HASHERS

PASSWORD_HASHERS = ('django.contrib.auth.hashers.UnsaltedMD5PasswordHasher',) + PASSWORD_HASHERS

A2_CACHE_ENABLED = False

LANGUAGE_CODE = 'en'
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'TEST': {
            'NAME': 'a2-test-%s' % os.environ.get("BRANCH_NAME", "").replace('/', '-'),
        },
    }
}
