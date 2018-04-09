import pytest

from django.core.urlresolvers import reverse

from authentic2.models import Attribute

import utils

pytestmark = pytest.mark.django_db


def test_account_edit_view(app, simple_user):
    utils.login(app, simple_user)
    url = reverse('profile_edit')
    resp = app.get(url, status=200)

    attribute = Attribute.objects.create(
        name='phone', label='phone',
        kind='string', user_visible=True, user_editable=True)

    resp = app.get(url, status=200)
    resp = app.post(url, params={
                        'csrfmiddlewaretoken': resp.form['csrfmiddlewaretoken'].value,
                        'edit-profile-first_name': resp.form['edit-profile-first_name'].value,
                        'edit-profile-last_name': resp.form['edit-profile-last_name'].value,
                        'edit-profile-phone': '1234'
                    },
                    status=302)
    # verify that missing next_url in POST is ok
    assert resp['Location'].endswith(reverse('account_management'))
    assert attribute.get_value(simple_user) == '1234'

    resp = app.get(url, status=200)
    resp.form.set('edit-profile-phone', '0123456789')
    resp = resp.form.submit().follow()
    assert attribute.get_value(simple_user) == '0123456789'

    resp = app.get(url, status=200)
    resp.form.set('edit-profile-phone', '9876543210')
    resp = resp.form.submit('cancel').follow()
    assert attribute.get_value(simple_user) == '0123456789'

    attribute.set_value(simple_user, '0123456789', verified=True)
    resp = app.get(url, status=200)
    resp.form.set('edit-profile-phone', '1234567890')
    assert 'readonly' in resp.form['edit-profile-phone'].attrs
    resp = resp.form.submit().follow()
    assert attribute.get_value(simple_user) == '0123456789'

    resp = app.get(url, status=200)
    assert 'phone' in resp
    assert 'readonly' in resp.form['edit-profile-phone'].attrs

    attribute.disabled = True
    attribute.save()
    resp = app.get(url, status=200)
    assert 'phone' not in resp
    assert attribute.get_value(simple_user) == '0123456789'


def test_account_edit_next_url(app, simple_user, external_redirect_next_url, assert_external_redirect):
    utils.login(app, simple_user)
    url = reverse('profile_edit')

    attribute = Attribute.objects.create(
        name='phone', label='phone',
        kind='string', user_visible=True,
        user_editable=True)

    resp = app.get(url + '?next=%s' % external_redirect_next_url, status=200)
    resp.form.set('edit-profile-phone', '0123456789')
    resp = resp.form.submit()
    assert_external_redirect(resp, reverse('account_management'))
    assert attribute.get_value(simple_user) == '0123456789'

    resp = app.get(url + '?next=%s' % external_redirect_next_url, status=200)
    resp.form.set('edit-profile-phone', '1234')
    resp = resp.form.submit('cancel')
    assert_external_redirect(resp, reverse('account_management'))
    assert attribute.get_value(simple_user) == '0123456789'


def test_account_edit_scopes(app, simple_user):
    utils.login(app, simple_user)
    url = reverse('profile_edit')

    Attribute.objects.create(name='phone', label='phone',
                             kind='string', user_visible=True,
                             user_editable=True, scopes='contact')
    Attribute.objects.create(name='mobile', label='mobile phone',
                             kind='string', user_visible=True,
                             user_editable=True, scopes='contact')

    Attribute.objects.create(name='city', label='city',
                             kind='string', user_visible=True,
                             user_editable=True, scopes='address')
    Attribute.objects.create(name='zipcode', label='zipcode', kind='string',
                             user_visible=True, user_editable=True,
                             scopes='address')

    def get_fields(resp):
        return set(key.split('edit-profile-')[1]
                   for key in resp.form.fields.keys() if key and key.startswith('edit-profile-'))
    resp = app.get(url, status=200)
    assert get_fields(resp) == set(['first_name', 'last_name', 'phone', 'mobile', 'city', 'zipcode', 'next_url'])

    resp = app.get(url + '?scope=contact', status=200)
    assert get_fields(resp) == set(['phone', 'mobile', 'next_url'])

    resp = app.get(url + '?scope=address', status=200)
    assert get_fields(resp) == set(['city', 'zipcode', 'next_url'])

    resp = app.get(url + '?scope=contact address', status=200)
    assert get_fields(resp) == set(['phone', 'mobile', 'city', 'zipcode', 'next_url'])

    resp = app.get(reverse('profile_edit_with_scope', kwargs={'scope': 'contact'}),
                   status=200)
    assert get_fields(resp) == set(['phone', 'mobile', 'next_url'])

    resp = app.get(reverse('profile_edit_with_scope', kwargs={'scope': 'address'}),
                   status=200)
    assert get_fields(resp) == set(['city', 'zipcode', 'next_url'])
