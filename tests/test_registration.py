# -*- coding: utf-8 -*-

import re
from urlparse import urlparse

from django.core.urlresolvers import reverse
from django.contrib.auth import get_user_model, REDIRECT_FIELD_NAME
from django.utils.http import urlquote

from authentic2 import utils, models

from utils import can_resolve_dns, get_link_from_mail


def test_registration(app, db, settings, mailoutbox, external_redirect):
    next_url, good_next_url = external_redirect

    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    User = get_user_model()
    url = utils.make_url('registration_register', params={REDIRECT_FIELD_NAME: next_url})
    response = app.get(url)
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()

    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert len(mailoutbox) == 1

    link = get_link_from_mail(mailoutbox[0])

    # test password validation
    response = app.get(link)
    response.form.set('password1', 'toto')
    response.form.set('password2', 'toto')
    response = response.form.submit()
    assert '8 characters' in response.content

    # set valid password
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    if good_next_url:
        assert 'You have just created an account.' in response.content
        assert next_url in response.content
    else:
        assert urlparse(response['Location']).path == '/'
        response = response.follow()
        assert 'You have just created an account.' in response.content
    assert User.objects.count() == 1
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body

    new_user = User.objects.get()
    assert new_user.email == 'testbot@entrouvert.com'
    assert new_user.username is None
    assert new_user.check_password('T0==toto')
    assert new_user.is_active
    assert not new_user.is_staff
    assert not new_user.is_superuser
    assert str(app.session['_auth_user_id']) == str(new_user.pk)

    response = app.get('/login/')
    response.form.set('username', 'testbot@entrouvert.com')
    response.form.set('password', 'T0==toto')
    response = response.form.submit(name='login-password-submit')
    assert urlparse(response['Location']).path == reverse('auth_homepage')


def test_registration_realm(app, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_REGISTRATION_REALM = 'realm'
    settings.A2_REDIRECT_WHITELIST = ['http://relying-party.org/']
    settings.A2_REQUIRED_FIELDS = ['username']

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    User = get_user_model()
    next_url = 'http://relying-party.org/'
    url = utils.make_url('registration_register', params={REDIRECT_FIELD_NAME: next_url})

    response = app.get(url)
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()

    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert '2 days' in response.content
    assert len(mailoutbox) == 1

    link = get_link_from_mail(mailoutbox[0])

    # register
    response = app.get(link)
    response.form.set('username', 'toto')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert 'You have just created an account.' in response.content
    assert next_url in response.content
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body

    # verify user has expected attributes
    new_user = User.objects.get()
    assert new_user.username == 'toto@realm'
    assert new_user.email == 'testbot@entrouvert.com'
    assert new_user.check_password('T0==toto')
    assert new_user.is_active
    assert not new_user.is_staff
    assert not new_user.is_superuser
    assert str(app.session['_auth_user_id']) == str(new_user.pk)

    # test login
    response = app.get('/login/')
    response.form.set('username', 'testbot@entrouvert.com')
    response.form.set('password', 'T0==toto')
    response = response.form.submit(name='login-password-submit')
    assert urlparse(response['Location']).path == reverse('auth_homepage')


def test_username_settings(app, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_REGISTRATION_FORM_USERNAME_REGEX = r'^(ab)+$'
    settings.A2_REGISTRATION_FORM_USERNAME_LABEL = 'Identifiant'
    settings.A2_REGISTRATION_FORM_USERNAME_HELP_TEXT = 'Bien remplir'
    settings.A2_REGISTRATION_FIELDS = ['username']
    settings.A2_REQUIRED_FIELDS = ['username']

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    response = app.get(reverse('registration_register'))
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert len(mailoutbox) == 1
    link = get_link_from_mail(mailoutbox[0])

    # register
    response = app.get(link)

    # check form render has changed
    assert response.pyquery('[for=id_username]').text() == 'Identifiant:'
    for key in ['username', 'password1', 'password2']:
        assert response.pyquery('[for=id_%s]' % key)
        assert response.pyquery('[for=id_%s]' % key).attr('class') == 'form-field-required'

    assert response.pyquery('#id_username').next('.helptext').text() == 'Bien remplir'
    assert not response.pyquery('.errorlist')

    # check username is validated using regexp
    response.form.set('username', 'abx')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()

    assert 'Enter a valid value' in response.content

    # check regexp accepts some valid values
    response.form.set('username', 'abab')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('auth_homepage')
    response = response.follow()
    assert 'You have just created an account.' in response.content
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body


def test_username_is_unique(app, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_REGISTRATION_FIELDS = ['username']
    settings.A2_REQUIRED_FIELDS = ['username']
    settings.A2_USERNAME_IS_UNIQUE = True

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    response = app.get(reverse('registration_register'))
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert len(mailoutbox) == 1

    link = get_link_from_mail(mailoutbox[0])

    response = app.get(link)
    response.form.set('username', 'john.doe')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('auth_homepage')
    response = response.follow()
    assert 'You have just created an account.' in response.content
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body

    # logout
    app.session.flush()

    # try again
    response = app.get(link)
    response = response.click('create')

    response.form.set('username', 'john.doe')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert ('This username is already in use. Please supply a different username.' in
            response.content)


def test_email_is_unique(app, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_EMAIL_IS_UNIQUE = True

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    response = app.get(reverse('registration_register'))
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert len(mailoutbox) == 1

    link = get_link_from_mail(mailoutbox[0])

    response = app.get(link)
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('auth_homepage')
    response = response.follow()
    assert 'You have just created an account.' in response.content
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body

    # logout
    app.session.flush()

    response = app.get(reverse('registration_register'))
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert not 'This email address is already in use.' in response.content
    assert len(mailoutbox) == 3
    assert 'You already have' in mailoutbox[2].body


def test_attribute_model(app, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    models.Attribute.objects.create(
        label=u'Prénom',
        name='prenom',
        required=True,
        kind='string')
    models.Attribute.objects.create(
        label=u'Nom',
        name='nom',
        asked_on_registration=True,
        user_visible=True,
        kind='string')
    models.Attribute.objects.create(
        label='Profession',
        name='profession',
        user_editable=True,
        kind='string')

    response = app.get(reverse('registration_register'))
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert len(mailoutbox) == 1

    link = get_link_from_mail(mailoutbox[0])

    response = app.get(link)

    for key in ['prenom', 'nom', 'password1', 'password2']:
        assert response.pyquery('#id_%s' % key)

    response.form.set('prenom', 'John')
    response.form.set('nom', 'Doe')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('auth_homepage')
    response = response.follow()
    assert 'You have just created an account.' in response.content
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body

    response = app.get(reverse('account_management'))

    assert 'Nom' in response.content
    assert 'Prénom' not in response.content

    response = app.get(reverse('profile_edit'))
    assert 'edit-profile-profession' in response.form.fields
    assert 'edit-profile-prenom' not in response.form.fields
    assert 'edit-profile-nom' not in response.form.fields

    assert response.pyquery('[for=id_edit-profile-profession]')
    assert not response.pyquery('[for=id_edit-profile-profession].form-field-required')
    response.form.set('edit-profile-profession', 'pompier')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('account_management')

    response = response.follow()

    assert 'Nom' in response.content
    assert 'Doe' in response.content
    assert 'Profession' not in response.content
    assert 'pompier' not in response.content
    assert 'Prénom' not in response.content
    assert 'John' not in response.content


def test_registration_email_blacklist(app, settings, db):
    def test_register(email):
        response = app.get('/accounts/register/')
        assert 'email' in response.form.fields
        response.form.set('email', email)
        response = response.form.submit()
        return response.status_code == 302
    settings.A2_REGISTRATION_EMAIL_BLACKLIST = ['a*@example\.com']
    assert not test_register('aaaa@example.com')
    assert test_register('aaaa@example.com.zob')
    assert test_register('baaaa@example.com')
    settings.A2_REGISTRATION_EMAIL_BLACKLIST = ['a*@example\.com', '^ba*@example\.com$']
    assert not test_register('aaaa@example.com')
    assert not test_register('baaaa@example.com')
    assert test_register('bbaaaa@example.com')


def test_registration_bad_email(app, db, settings):
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.LANGUAGE_CODE = 'en-us'

    response = app.post(reverse('registration_register'), params={'email': 'fred@0d..be'},
                        status=200)
    assert 'Enter a valid email address.' in response.context['form'].errors['email']

    response = app.post(reverse('registration_register'), params={'email': u'ééééé'}, status=200)
    assert 'Enter a valid email address.' in response.context['form'].errors['email']

    response = app.post(reverse('registration_register'), params={'email': u''}, status=200)
    assert 'This field is required.' in response.context['form'].errors['email']


def test_registration_confirm_data(app, settings, db, rf):
    # make first name not required
    models.Attribute.objects.filter(
        name='first_name').update(
            required=False)

    activation_url = utils.build_activation_url(
        rf.post('/accounts/register/'),
        email='john.doe@example.com',
        next_url='/',
        first_name='John',
        last_name='Doe',
        no_password=True,
        confirm_data=False)

    response = app.get(activation_url, status=302)

    activation_url = utils.build_activation_url(
        rf.post('/accounts/register/'),
        email='john.doe@example.com',
        next_url='/',
        last_name='Doe',
        no_password=True,
        confirm_data=False)

    response = app.get(activation_url, status=200)
    assert 'form' in response.context
    assert set(response.context['form'].fields.keys()) == set(['first_name', 'last_name'])

    activation_url = utils.build_activation_url(
        rf.post('/accounts/register/'),
        email='john.doe@example.com',
        next_url='/',
        last_name='Doe',
        no_password=True,
        confirm_data='required')
    response = app.get(activation_url, status=302)


def test_revalidate_email(app, rf, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)
    url = utils.build_activation_url(
        rf.get('/'),
        'testbot@entrouvert.com',
        next_url=None,
        valid_email=False,
        franceconnect=True)

    assert len(mailoutbox) == 0
    # register
    response = app.get(url)
    response.form.set('email', 'johndoe@example.com')
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert urlparse(response['Location']).path == reverse('registration_complete')
    response = response.follow()
    assert '2 days' in response.content
    assert 'johndoe@example.com' in response.content
    assert len(mailoutbox) == 1


def test_email_is_unique_multiple_objects_returned(app, db, settings, mailoutbox, rf):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_REGISTRATION_EMAIL_IS_UNIQUE = True

    # Create two user objects
    User = get_user_model()
    User.objects.create(email='testbot@entrouvert.com')
    User.objects.create(email='testbot@entrouvert.com')

    url = utils.build_activation_url(
        rf.get('/'),
        'testbot@entrouvert.com',
        first_name='Test',
        last_name='Bot',
        password='ABcd12345',
        next_url=None,
        valid_email=False,
        franceconnect=True)

    response = app.get(url)
    assert 'This email address is already in use.' in response.content


def test_username_is_unique_multiple_objects_returned(app, db, settings, mailoutbox, rf):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_REGISTRATION_USERNAME_IS_UNIQUE = True
    settings.A2_REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    # Create two user objects
    User = get_user_model()
    User.objects.create(username='testbot', email='testbot1@entrouvert.com')
    User.objects.create(username='testbot', email='testbot2@entrouvert.com')

    url = utils.build_activation_url(
        rf.get('/'),
        'testbot@entrouvert.com',
        username='testbot',
        first_name='Test',
        last_name='Bot',
        password='ABcd12345',
        next_url=None,
        valid_email=False,
        franceconnect=True)

    response = app.get(url)
    assert 'This username is already in use.' in response.content


def test_registration_redirect(app, db, settings, mailoutbox, external_redirect):
    next_url, good_next_url = external_redirect

    settings.A2_REGISTRATION_REDIRECT = 'http://cms/welcome/'
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()

    new_next_url = settings.A2_REGISTRATION_REDIRECT
    if good_next_url:
        new_next_url += '?next=' + urlquote(next_url)

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    User = get_user_model()
    url = utils.make_url('registration_register', params={REDIRECT_FIELD_NAME: next_url})
    response = app.get(url)
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()

    assert urlparse(response['Location']).path == reverse('registration_complete')

    response = response.follow()
    assert '2 days' in response.content
    assert 'testbot@entrouvert.com' in response.content
    assert len(mailoutbox) == 1

    link = get_link_from_mail(mailoutbox[0])
    response = app.get(link)
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()

    assert 'You have just created an account.' in response.content
    assert new_next_url in response.content

    assert User.objects.count() == 1
    assert len(mailoutbox) == 2
    assert 'was successful' in mailoutbox[1].body

    new_user = User.objects.get()
    assert new_user.email == 'testbot@entrouvert.com'
    assert new_user.username is None
    assert new_user.check_password('T0==toto')
    assert new_user.is_active
    assert not new_user.is_staff
    assert not new_user.is_superuser
    assert str(app.session['_auth_user_id']) == str(new_user.pk)

    response = app.get('/login/')
    response.form.set('username', 'testbot@entrouvert.com')
    response.form.set('password', 'T0==toto')
    response = response.form.submit(name='login-password-submit')
    assert urlparse(response['Location']).path == reverse('auth_homepage')


def test_registration_redirect_tuple(app, db, settings, mailoutbox, external_redirect):
    next_url, good_next_url = external_redirect

    settings.A2_REGISTRATION_REDIRECT = 'http://cms/welcome/', 'target'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()

    new_next_url = settings.A2_REGISTRATION_REDIRECT[0]
    if good_next_url:
        new_next_url += '?target=' + urlquote(next_url)

    # disable existing attributes
    models.Attribute.objects.update(disabled=True)

    url = utils.make_url('registration_register', params={REDIRECT_FIELD_NAME: next_url})
    response = app.get(url)
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    response = response.follow()
    link = get_link_from_mail(mailoutbox[0])
    response = app.get(link)
    response.form.set('password1', 'T0==toto')
    response.form.set('password2', 'T0==toto')
    response = response.form.submit()
    assert new_next_url in response.content


def test_registration_activate_passwords_not_equal(app, db, settings, mailoutbox):
    settings.LANGUAGE_CODE = 'en-us'
    settings.A2_VALIDATE_EMAIL_DOMAIN = can_resolve_dns()
    settings.A2_EMAIL_IS_UNIQUE = True

    response = app.get(reverse('registration_register'))
    response.form.set('email', 'testbot@entrouvert.com')
    response = response.form.submit()
    response = response.follow()
    link = get_link_from_mail(mailoutbox[0])
    response = app.get(link)
    response.form.set('password1', 'azerty12AZ')
    response.form.set('password2', 'AAAazerty12AZ')
    response = response.form.submit()
    assert "The two password fields didn&#39;t match." in response.content


def test_authentication_method(app, db, rf, hooks):
    activation_url = utils.build_activation_url(
        rf.post('/accounts/register/'),
        email='john.doe@example.com',
        next_url='/',
        first_name='John',
        last_name='Doe',
        no_password=True,
        confirm_data=False)
    app.get(activation_url)

    assert len(hooks.calls['event']) == 2
    assert hooks.calls['event'][-2]['kwargs']['name'] == 'registration'
    assert hooks.calls['event'][-2]['kwargs']['authentication_method'] == 'email'
    assert hooks.calls['event'][-1]['kwargs']['name'] == 'login'
    assert hooks.calls['event'][-1]['kwargs']['how'] == 'email'

    activation_url = utils.build_activation_url(
        rf.post('/accounts/register/'),
        email='jane.doe@example.com',
        next_url='/',
        first_name='Jane',
        last_name='Doe',
        no_password=True,
        authentication_method='another',
        confirm_data=False)
    app.get(activation_url)

    assert len(hooks.calls['event']) == 4
    assert hooks.calls['event'][-2]['kwargs']['name'] == 'registration'
    assert hooks.calls['event'][-2]['kwargs']['authentication_method'] == 'another'
    assert hooks.calls['event'][-1]['kwargs']['name'] == 'login'
    assert hooks.calls['event'][-1]['kwargs']['how'] == 'another'
