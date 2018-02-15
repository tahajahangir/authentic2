from django.core.urlresolvers import reverse

from authentic2.models import Attribute
from authentic2.a2_rbac.utils import get_default_ou
from utils import login, get_link_from_mail


def visible_users(response):
    return set(elt.text for elt in response.pyquery('td.username'))


def test_manager_user_change_email(app, superuser_or_admin, simple_user, mailoutbox):
    ou = get_default_ou()
    ou.validate_emails = True
    ou.save()

    NEW_EMAIL = 'john.doe@example.com'

    assert NEW_EMAIL != simple_user.email

    response = login(app, superuser_or_admin,
                     reverse('a2-manager-user-by-uuid-detail',
                             kwargs={'slug': unicode(simple_user.uuid)}))
    assert 'Change user email' in response.content
    # cannot click it's a submit button :/
    response = app.get(reverse('a2-manager-user-by-uuid-change-email',
                               kwargs={'slug': unicode(simple_user.uuid)}))
    assert response.form['new_email'].value == simple_user.email
    response.form.set('new_email', NEW_EMAIL)
    assert len(mailoutbox) == 0
    response = response.form.submit().follow()
    assert 'A mail was sent to john.doe@example.com to verify it.' in response.content
    assert 'Change user email' in response.content
    # cannot click it's a submit button :/
    assert len(mailoutbox) == 1
    assert simple_user.email in mailoutbox[0].body
    assert NEW_EMAIL in mailoutbox[0].body

    # logout
    app.session.flush()

    link = get_link_from_mail(mailoutbox[0])
    response = app.get(link).maybe_follow()
    assert (
        'your request for changing your email for john.doe@example.com is successful'
        in response.content)
    simple_user.refresh_from_db()
    assert simple_user.email == NEW_EMAIL


def test_manager_user_change_email_no_change(app, superuser_or_admin, simple_user, mailoutbox):
    ou = get_default_ou()
    ou.validate_emails = True
    ou.save()

    NEW_EMAIL = 'john.doe@example.com'

    assert NEW_EMAIL != simple_user.email

    response = login(app, superuser_or_admin,
                     reverse('a2-manager-user-by-uuid-detail',
                             kwargs={'slug': unicode(simple_user.uuid)}))
    assert 'Change user email' in response.content
    # cannot click it's a submit button :/
    response = app.get(reverse('a2-manager-user-by-uuid-change-email',
                               kwargs={'slug': unicode(simple_user.uuid)}))
    assert response.form['new_email'].value == simple_user.email
    assert len(mailoutbox) == 0
    response = response.form.submit().follow()
    assert 'A mail was sent to john.doe@example.com to verify it.' not in response.content


def test_search_by_attribute(app, simple_user, admin):
    Attribute.objects.create(name='adresse', searchable=True, kind='string')

    simple_user.attributes.adresse = 'avenue du revestel'
    response = login(app, admin, '/manage/users/')

    # all users are visible
    assert visible_users(response) == {simple_user.username, admin.username}

    response.form['search-text'] = 'impasse'
    response = response.form.submit()
    # now all users are hidden
    assert not visible_users(response) & {simple_user.username, admin.username}

    response.form['search-text'] = 'avenue'
    response = response.form.submit()

    # now we see only simple_user
    assert visible_users(response) == {simple_user.username}
