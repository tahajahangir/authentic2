import os

# use a faster hasing scheme for passwords
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.UnsaltedMD5PasswordHasher',
]

LANGUAGE_CODE = 'en'
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'TEST': {
            'NAME': 'a2-test',
        },
    }
}
