import csv

from django.core.urlresolvers import reverse

from django.contrib.contenttypes.models import ContentType

from authentic2.custom_user.models import User
from authentic2.models import Attribute, AttributeValue
from authentic2.a2_rbac.utils import get_default_ou

from utils import login, get_link_from_mail, skipif_sqlite



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


@skipif_sqlite
def test_export_csv(settings, app, superuser, django_assert_num_queries):
    AT_COUNT = 30
    USER_COUNT = 2000
    DEFAULT_BATCH_SIZE = 1000

    ats = [Attribute(name='at%s' % i, label='At%s' % i, kind='string') for i in range(AT_COUNT)]
    Attribute.objects.bulk_create(ats)

    ats = list(Attribute.objects.all())
    users = [User(username='user%s' % i) for i in range(USER_COUNT)]
    User.objects.bulk_create(users)
    users = list(User.objects.filter(username__startswith='user'))

    user_ct = ContentType.objects.get_for_model(User)
    atvs = []
    for i in range(USER_COUNT):
        atvs.extend([AttributeValue(
            owner=users[i], attribute=ats[j], content='value-%s-%s' % (i, j)) for j in range(AT_COUNT)])
    AttributeValue.objects.bulk_create(atvs)

    response = login(app, superuser, reverse('a2-manager-users'))
    settings.A2_CACHE_ENABLED = True
    user_count = User.objects.count()
    # queries should be batched to keep prefetching working without
    # overspending memory for the queryset cache, 4 queries by batches
    num_queries = 9 + 4 * (user_count / DEFAULT_BATCH_SIZE + bool(user_count % DEFAULT_BATCH_SIZE))
    with django_assert_num_queries(num_queries):
         response = response.click('CSV')
    table = list(csv.reader(response.content.splitlines()))
    assert len(table) == (user_count + 1)
    assert len(table[0]) == (15 + AT_COUNT)

