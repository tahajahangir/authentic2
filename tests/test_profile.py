import pytest

from django.core.urlresolvers import reverse

from authentic2.models import Attribute

import utils

pytestmark = pytest.mark.django_db


def test_account_edit_view(app, simple_user):
    utils.login(app, simple_user)
    url = reverse('profile_edit')
    resp = app.get(url, status=200)

    attribute = Attribute.objects.create(name='phone', label='phone',
        kind='string', user_visible=True, user_editable=True)
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
