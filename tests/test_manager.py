import pytest
import json
from urlparse import urlparse

from django.core.urlresolvers import reverse
from django.core import mail

from webtest import Upload

from authentic2.a2_rbac.utils import get_default_ou

from django_rbac.utils import get_ou_model, get_role_model
from django.contrib.auth import get_user_model
from utils import login, get_link_from_mail


pytestmark = pytest.mark.django_db


def test_manager_login(superuser_or_admin, app):
    manager_home_page = login(app, superuser_or_admin, reverse('a2-manager-homepage'))

    sections = ['users', 'roles', 'ous']
    no_sections = ['services']
    if superuser_or_admin.is_superuser:
        sections += no_sections
        no_sections = []

    for section in sections:
        path = reverse('a2-manager-%s' % section)
        assert manager_home_page.pyquery.remove_namespaces()('.apps a[href=\'%s\']' % path)
    for section in no_sections:
        path = reverse('a2-manager-%s' % section)
        assert not manager_home_page.pyquery.remove_namespaces()('.apps a[href=\'%s\']' % path)


def test_manager_create_ou(superuser_or_admin, app):
    OU = get_ou_model()

    ou_add = login(app, superuser_or_admin, path=reverse('a2-manager-ou-add'))
    form = ou_add.form
    form.set('name', 'New OU')
    response = form.submit().follow()
    assert 'New OU' in response
    assert OU.objects.count() == 2
    assert OU.objects.get(name='New OU').slug == 'new-ou'

    # Test slug collision
    OU.objects.filter(name='New OU').update(name='Old OU')
    response = form.submit().follow()
    assert 'Old OU' in response
    assert 'New OU' in response
    assert OU.objects.get(name='Old OU').slug == 'new-ou'
    assert OU.objects.get(name='New OU').slug == 'new-ou1'
    assert OU.objects.count() == 3


def test_manager_create_role(superuser_or_admin, app):
    # clear cache from previous runs
    from authentic2.manager.utils import get_ou_count
    get_ou_count.cache.cache = {}

    Role = get_role_model()
    OU = get_ou_model()

    non_admin_roles = Role.objects.exclude(slug__startswith='_')

    ou_add = login(app, superuser_or_admin, reverse('a2-manager-role-add'))
    form = ou_add.form
    assert 'name' in form.fields
    assert 'description' in form.fields
    assert 'ou' not in form.fields
    form.set('name', 'New role')
    response = form.submit().follow()
    assert non_admin_roles.count() == 1
    role = non_admin_roles.get()
    assert response.request.path == reverse('a2-manager-role-members', kwargs={'pk': role.pk})
    role_list = app.get(reverse('a2-manager-roles'))
    assert 'New role' in role_list 

    # Test slug collision
    non_admin_roles.update(name='Old role')
    response = form.submit().follow()
    role_list = app.get(reverse('a2-manager-roles'))
    assert 'New role' in role_list 
    assert 'Old role' in role_list
    assert non_admin_roles.count() == 2
    assert non_admin_roles.get(name='New role').slug == 'new-role1'
    assert non_admin_roles.get(name='Old role').slug == 'new-role'

    # Test multi-ou form
    OU.objects.create(name='New OU', slug='new-ou')
    ou_add = app.get(reverse('a2-manager-role-add'))
    form = ou_add.form
    assert 'name' in form.fields
    assert 'description' in form.fields
    assert 'ou' in form.fields
    options = [o[2] for o in form.fields['ou'][0].options]
    assert len(options) == 3
    assert '---------' in options
    assert 'New OU' in options


def test_manager_user_password_reset(app, superuser, simple_user):
    resp = login(app, superuser,
                 reverse('a2-manager-user-detail', kwargs={'pk': simple_user.pk}))
    assert len(mail.outbox) == 0
    resp = resp.form.submit('password_reset')
    assert 'A mail was sent to' in resp
    assert len(mail.outbox) == 1
    url = get_link_from_mail(mail.outbox[0])
    relative_url = url.split('testserver')[1]
    resp = app.get('/logout/').maybe_follow()
    resp = app.get(relative_url, status=200)
    resp.form.set('new_password1', '1234==aA')
    resp.form.set('new_password2', '1234==aA')
    resp = resp.form.submit().follow()
    assert str(app.session['_auth_user_id']) == str(simple_user.pk)


def test_manager_user_detail_by_uuid(app, superuser, simple_user):
    url = reverse('a2-manager-user-by-uuid-detail', kwargs={'slug': simple_user.uuid})
    resp = login(app, superuser, url)
    assert '<strong>Actions</strong>' in resp.content
    assert simple_user.first_name.encode('utf-8') in resp.content


def test_manager_user_edit_by_uuid(app, superuser, simple_user):
    url = reverse('a2-manager-user-by-uuid-edit', kwargs={'slug': simple_user.uuid})
    resp = login(app, superuser, url)
    assert '<strong>Actions</strong>' not in resp.content
    assert simple_user.first_name.encode('utf-8') in resp.content


def test_manager_stress_create_user(superuser_or_admin, app, mailoutbox):
    User = get_user_model()
    OU = get_ou_model()

    new_ou = OU.objects.create(name='new ou', slug='new-ou')
    url = reverse('a2-manager-user-add', kwargs={'ou_pk': new_ou.pk})
    # create first user with john.doe@gmail.com ou OU1 : OK

    assert len(mailoutbox) == 0
    assert User.objects.filter(ou_id=new_ou.id).count() == 0
    for i in range(100):
        ou_add = login(app, superuser_or_admin, url)
        form = ou_add.form
        form.set('first_name', 'John')
        form.set('last_name', 'Doe')
        form.set('email', 'john.doe@gmail.com')
        form.set('password1', 'ABcd1234')
        form.set('password2', 'ABcd1234')
        form.submit().follow()
        app.get('/logout/').form.submit()
    assert User.objects.filter(ou_id=new_ou.id).count() == 100
    assert len(mailoutbox) == 100


def test_role_members_from_ou(app, superuser, settings):
    Role = get_role_model()
    r = Role.objects.create(name='role', slug='role', ou=get_default_ou())
    url = reverse('a2-manager-role-members', kwargs={'pk': r.pk})
    response = login(app, superuser, url)
    assert not response.context['form'].fields['user'].queryset.query.where
    settings.A2_MANAGER_ROLE_MEMBERS_FROM_OU = True
    response = app.get(url)
    assert response.context['form'].fields['user'].queryset.query.where


def test_role_members_show_all_ou(app, superuser, settings):
    Role = get_role_model()
    r = Role.objects.create(name='role', slug='role', ou=get_default_ou())
    url = reverse('a2-manager-role-members', kwargs={'pk': r.pk})
    response = login(app, superuser, url)
    assert not response.context['form'].fields['user'].queryset.query.where
    settings.A2_MANAGER_ROLE_MEMBERS_FROM_OU = True
    response = app.get(url)
    assert response.context['form'].fields['user'].queryset.query.where


def test_manager_create_user(superuser_or_admin, app, settings):
    # clear cache from previous runs
    from authentic2.manager.utils import get_ou_count
    get_ou_count.cache.clear()

    User = get_user_model()
    OU = get_ou_model()
    ou1 = OU.objects.create(name='OU1', slug='ou1')
    ou2 = OU.objects.create(name='OU2', slug='ou2', email_is_unique=True)

    assert User.objects.filter(ou=ou1).count() == 0
    assert User.objects.filter(ou=ou2).count() == 0

    # create first user with john.doe@gmail.com ou OU1 : OK
    url = reverse('a2-manager-user-add', kwargs={'ou_pk': ou1.pk})
    ou_add = login(app, superuser_or_admin, url)
    form = ou_add.form
    form.set('first_name', 'John')
    form.set('last_name', 'Doe')
    form.set('email', 'john.doe@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit().follow()
    assert User.objects.filter(ou=ou1).count() == 1

    # create second user with john.doe@gmail.com ou OU1 : OK
    ou_add = app.get(url)
    form = ou_add.form
    form.set('first_name', 'John')
    form.set('last_name', 'Doe')
    form.set('email', 'john.doe@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit().follow()
    assert User.objects.filter(ou=ou1).count() == 2

    # create first user with john.doe@gmail.com ou OU2 : OK
    url = reverse('a2-manager-user-add', kwargs={'ou_pk': ou2.pk})
    ou_add = app.get(url)
    form = ou_add.form
    form.set('first_name', 'John')
    form.set('last_name', 'Doe')
    form.set('email', 'john.doe@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit().follow()
    assert User.objects.filter(ou=ou2).count() == 1

    # create second user with john.doe@gmail.com ou OU2 : NOK
    ou_add = app.get(url)
    form = ou_add.form
    form.set('first_name', 'John')
    form.set('last_name', 'Doe')
    form.set('email', 'john.doe@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit()
    assert User.objects.filter(ou=ou2).count() == 1
    assert 'Email already used' in response

    # create first user with john.doe2@gmail.com ou OU2 : OK
    ou_add = app.get(url)
    form = ou_add.form
    form.set('first_name', 'Jane')
    form.set('last_name', 'Doe')
    form.set('email', 'john.doe2@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit().follow()
    assert User.objects.filter(ou=ou2).count() == 2

    # try to change user email from john.doe2@gmail.com to
    # john.doe@gmail.com in OU2 : NOK
    response.form.set('email', 'john.doe@gmail.com')
    response = form.submit()
    assert 'Email already used' in response

    # create first user with email john.doe@gmail.com in OU1: NOK
    settings.A2_EMAIL_IS_UNIQUE = True
    url = reverse('a2-manager-user-add', kwargs={'ou_pk': ou1.pk})
    User.objects.filter(ou=ou1).delete()
    assert User.objects.filter(ou=ou1).count() == 0
    ou_add = app.get(url)
    form = ou_add.form
    form.set('first_name', 'John')
    form.set('last_name', 'Doe')
    form.set('email', 'john.doe@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit()
    assert User.objects.filter(ou=ou1).count() == 0
    assert 'Email already used' in response
    form = response.form
    form.set('email', 'john.doe3@gmail.com')
    form.set('password1', 'ABcd1234')
    form.set('password2', 'ABcd1234')
    response = form.submit().follow()
    assert User.objects.filter(ou=ou1).count() == 1

    # try to change user email from john.doe3@gmail.com to
    # john.doe@gmail.com in OU2 : NOK
    response.form.set('email', 'john.doe@gmail.com')
    response = form.submit()
    assert 'Email already used' in response


def test_app_setting_login_url(app, settings):
    settings.A2_MANAGER_LOGIN_URL = '/other_login/'
    response = app.get('/manage/')
    assert urlparse(response['Location']).path == settings.A2_MANAGER_LOGIN_URL
    assert urlparse(response['Location']).query == 'next=/manage/'


def test_manager_one_ou(app, superuser, admin, simple_role, settings):
    def test_user_listing(user):
        response = login(app, user, '/manage/')

        # test user listing ou search
        response = response.click(href='users')
        assert 'search-ou' not in response.form.fields
        assert len(response.form.fields['search-text']) == 1
        # verify table shown
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 2
        assert set([e.text for e in q('table tbody td.username')]) == {'admin', 'superuser'}

        # test user's role page
        response = app.get('/manage/users/%d/roles/' % admin.pk)
        form = response.forms['search-form']
        assert 'search-ou' not in form.fields
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        assert q('table tbody tr').text() == u'simple role'

        form.set('search-internals', True)
        response = form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 5
        # admin enroled only in the Manager role, other roles are inherited
        assert len(q('table tbody tr td.via')) == 5
        assert len(q('table tbody tr td.via:empty')) == 2
        for elt in q('table tbody td.name a'):
            assert 'Manager' in elt.text or elt.text == 'simple role'

        # test role listing
        response = app.get('/manage/roles/')
        assert 'search-ou' not in response.form.fields
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        assert q('table tbody td.name').text() == u'simple role'

        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 5
        for elt in q('table tbody td.name a'):
            assert 'Manager' in elt.text or elt.text == u'simple role'

    test_user_listing(admin)
    app.session.flush()
    test_user_listing(superuser)


def test_manager_many_ou(app, superuser, admin, simple_role, role_ou1, admin_ou1, settings, ou1):
    def test_user_listing_admin(user):
        response = login(app, user, '/manage/')

        # test user listing ou search
        response = response.click(href='users')
        assert len(response.form.fields['search-ou']) == 1
        assert len(response.form.fields['search-text']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 4
        for key, checked, label in options:
            assert not checked or key == 'all'
        assert 'all' in [o[0] for o in options]
        assert 'none' in [o[0] for o in options]
        # verify table shown
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 3
        assert set([e.text for e in q('table tbody td.username')]) == {'admin', 'superuser',
                                                                       'admin.ou1'}

        # test user's role page
        response = app.get('/manage/users/%d/roles/' % admin.pk)
        assert len(response.form.fields['search-ou']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 4
        for key, checked, label in options:
            assert not checked or key == str(get_default_ou().pk)
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        assert q('table tbody tr').text() == u'simple role'

        response.form.set('search-ou', 'all')
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        assert q('table tbody tr').text() == 'None'

        form = response.forms['search-form']
        form.set('search-internals', True)
        response = form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 4
        # admin enroled only in the Manager role, other roles are inherited
        assert len(q('table tbody tr td.via')) == 4
        assert len(q('table tbody tr td.via:empty')) == 1
        for elt in q('table tbody td.name a'):
            assert 'Manager' in elt.text

        form = response.forms['search-form']
        form.set('search-ou', 'none')
        form.set('search-internals', True)
        response = form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 6
        for elt in q('table tbody td.name a'):
            assert 'Manager' in elt.text

        # test role listing
        response = app.get('/manage/roles/')
        assert len(response.form.fields['search-ou']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 4
        for key, checked, label in options:
            if key == 'all':
                assert checked
            else:
                assert not checked
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 2
        names = [elt.text for elt in q('table tbody td.name a')]
        assert set(names) == {u'simple role', u'role_ou1'}

        response.form.set('search-ou', 'all')
        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 12
        for elt in q('table tbody td.name a'):
            assert ('OU1' in elt.text or 'Default' in elt.text or 'Manager' in elt.text
                    or elt.text == u'simple role' or elt.text == u'role_ou1')

        response.form.set('search-ou', 'none')
        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 6
        for elt in q('table tbody td.name a'):
            assert 'Manager' in elt.text

    test_user_listing_admin(admin)
    app.session.flush()

    test_user_listing_admin(superuser)
    app.session.flush()

    def test_user_listing_ou_admin(user):
        response = login(app, user, '/manage/')

        # test user listing ou search
        response = response.click(href='users')
        assert len(response.form.fields['search-ou']) == 1
        assert len(response.form.fields['search-text']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 1
        # ou1 is selected
        key, checked, label = options[0]
        assert checked
        assert key == str(ou1.pk)
        # verify table shown
        q = response.pyquery.remove_namespaces()
        # only admin.ou1 is visible
        assert len(q('table tbody tr')) == 1
        assert set([e.text for e in q('table tbody td.username')]) == {'admin.ou1'}

        # test user's role page
        response = app.get('/manage/users/%d/roles/' % admin.pk)
        assert len(response.form.fields['search-ou']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 1
        key, checked, label = options[0]
        assert checked
        assert key == str(ou1.pk)
        q = response.pyquery.remove_namespaces()
        # only role_ou1 is visible
        assert len(q('table tbody tr')) == 1
        assert q('table tbody tr').text() == role_ou1.name

        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 3
        names = {elt.text for elt in q('table tbody td.name a')}
        assert names == {'Roles - OU1', 'Users - OU1', 'role_ou1'}

        # test role listing
        response = app.get('/manage/roles/')
        assert len(response.form.fields['search-ou']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 1
        key, checked, label = options[0]
        assert checked
        assert key == str(ou1.pk)
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        names = [elt.text for elt in q('table tbody td.name a')]
        assert set(names) == {u'role_ou1'}

        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 3
        names = {elt.text for elt in q('table tbody td.name a')}
        assert names == {'Roles - OU1', 'Users - OU1', 'role_ou1'}

    test_user_listing_ou_admin(admin_ou1)


def test_manager_many_ou_auto_admin_role(app, ou1, admin, user_with_auto_admin_role, auto_admin_role):
    def test_user_listing_auto_admin_role(user):
        response = login(app, user, '/manage/')

        # users are not visible
        with pytest.raises(IndexError):
            response = response.click(href='users')

        # test user's role page
        response = app.get('/manage/users/%d/roles/' % admin.pk)
        assert len(response.form.fields['search-ou']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 1
        key, checked, label = options[0]
        assert checked
        assert key == str(ou1.pk)
        q = response.pyquery.remove_namespaces()
        # only role_ou1 is visible
        assert len(q('table tbody tr')) == 1
        assert q('table tbody tr').text() == auto_admin_role.name

        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        names = {elt.text for elt in q('table tbody td.name a')}
        assert names == {'Auto Admin Role'}

        # test role listing
        response = app.get('/manage/roles/')
        assert len(response.form.fields['search-ou']) == 1
        field = response.form['search-ou']
        options = field.options
        assert len(options) == 1
        key, checked, label = options[0]
        assert checked
        assert key == str(ou1.pk)
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        names = [elt.text for elt in q('table tbody td.name a')]
        assert set(names) == {u'Auto Admin Role'}

        response.form.set('search-internals', True)
        response = response.form.submit()
        q = response.pyquery.remove_namespaces()
        assert len(q('table tbody tr')) == 1
        names = {elt.text for elt in q('table tbody td.name a')}
        assert set(names) == {u'Auto Admin Role'}

    test_user_listing_auto_admin_role(user_with_auto_admin_role)


def test_manager_site_export(app, superuser):
    response = login(app, superuser, '/manage/site-export/')
    assert 'roles' in response.json
    assert 'ous' in response.json


def test_manager_site_export_forbidden(app, simple_user):
    login(app, simple_user)
    app.get('/manage/site-export/', status=403)


def test_manager_site_import(app, db, superuser):
    site_import = login(app, superuser, '/manage/site-import/')
    form = site_import.form
    site_export = {
        'roles': [
            {
                "description": "", "service": None, "name": "basic",
                "attributes": [],
                "ou": {
                    "slug": "default",
                    "uuid": "ba60d9e6c2874636883bdd604b23eab2",
                    "name": "Collectivit\u00e9 par d\u00e9faut"
                },
                "external_id": "",
                "slug": "basic",
                "uuid": "6eb7bbf64bf547119120f925f0e560ac"
            }]
    }
    form['site_json'] = Upload(
        'site_export.json', json.dumps(site_export), 'application/octet-stream')
    res = form.submit()
    assert res.status_code == 302
    assert get_role_model().objects.get(slug='basic')


def test_manager_site_import_error(app, db, superuser):
    site_import = login(app, superuser, '/manage/site-import/')
    form = site_import.form
    site_export = {
        'roles': [
            {
                "description": "", "service": None, "name": "basic",
                "attributes": [],
                "ou": {
                    "slug": "unkown-ou",
                    "uuid": "ba60d9e6c2874636883bdd604b23eab2",
                    "name": "unkown ou"
                },
                "external_id": "",
                "slug": "basic",
                "uuid": "6eb7bbf64bf547119120f925f0e560ac"
            }]
    }
    form['site_json'] = Upload(
        'site_export.json', json.dumps(site_export), 'application/octet-stream')
    res = form.submit()
    assert res.status_code == 200
    assert 'missing Organizational Unit' in res.text
    Role = get_role_model()
    with pytest.raises(Role.DoesNotExist):
        Role.objects.get(slug='basic')


def test_manager_site_import_forbidden(app, simple_user):
    login(app, simple_user)
    app.get('/manage/site-import/', status=403)


def test_manager_homepatge_import_export(superuser, app):
    manager_home_page = login(app, superuser, reverse('a2-manager-homepage'))
    assert 'site-import' in manager_home_page.text
    assert 'site-export' in manager_home_page.text


def test_manager_homepatge_import_export_hidden(admin, app):
    manager_home_page = login(app, admin, reverse('a2-manager-homepage'))
    assert 'site-import' not in manager_home_page.text
    assert 'site-export' not in manager_home_page.text


def test_manager_ou(app, superuser_or_admin, ou1):
    OU = get_ou_model()

    manager_home_page = login(app, superuser_or_admin, reverse('a2-manager-homepage'))
    ou_homepage = manager_home_page.click(href='organizational-units')
    assert set([e.text for e in ou_homepage.pyquery('td.name')]) == set(['OU1', 'Default organizational unit'])

    # add a new ou
    add_ou_page = ou_homepage.click('Add')
    add_ou_page.form.set('name', 'ou2')
    add_ou_page.form.set('default', True)
    ou_homepage = add_ou_page.form.submit().follow()
    ou2 = OU.objects.get(name='ou2')
    assert set([e.text for e in ou_homepage.pyquery('td.name')]) == set(['OU1', 'Default organizational unit', 'ou2'])
    assert len(ou_homepage.pyquery('tr[data-pk="%s"] td.default span.true' % ou2.pk)) == 1

    # FIXME: table lines are not clickable as they do not contain an anchor
    # default ou cannot be deleted
    ou2_detail_page = app.get(reverse('a2-manager-ou-detail', kwargs={'pk': ou2.pk}))
    assert ou2_detail_page.pyquery('a.disabled').text() == 'Delete'

    # but ou1 can be deleted
    ou1_detail_page = app.get(reverse('a2-manager-ou-detail', kwargs={'pk': ou1.pk}))
    ou1_delete_page = ou1_detail_page.click('Delete')
    ou_homepage = ou1_delete_page.form.submit().follow()
    assert set([e.text for e in ou_homepage.pyquery('td.name')]) == set(['Default organizational unit', 'ou2'])

    # remake old default ou the default one
    old_default = OU.objects.get(name__contains='Default')
    old_default_detail_page = app.get(reverse('a2-manager-ou-detail', kwargs={'pk': old_default.pk}))
    assert not old_default_detail_page.pyquery('input[name="default"][checked="checked"]')
    old_default_edit_page = old_default_detail_page.click('Edit')
    old_default_edit_page.form.set('default', True)
    old_default_detail_page = old_default_edit_page.form.submit().follow()
    # check detail page has changed
    assert old_default_detail_page.pyquery('input[name="default"][checked="checked"]')
    # check ou homepage has changed too
    ou_homepage = old_default_detail_page.click('Organizational unit')
    assert set([e.text for e in ou_homepage.pyquery('td.name')]) == set(['Default organizational unit', 'ou2'])
    assert len(ou_homepage.pyquery('span.true')) == 1
    assert len(ou_homepage.pyquery('tr[data-pk="%s"] td.default span.true' % ou2.pk)) == 0
    assert len(ou_homepage.pyquery('tr[data-pk="%s"] td.default span.true' % old_default.pk)) == 1


def test_return_on_logout(superuser, app):
    '''Verify we will return to /manage/ after logout/login cycle'''
    manager_home_page = login(app, superuser, reverse('a2-manager-homepage'))
    response = manager_home_page.click('Logout').maybe_follow()
    assert response.request.query_string == 'next=/manage/'
