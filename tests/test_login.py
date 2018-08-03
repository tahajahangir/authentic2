import pytest
from urllib import quote

from django.contrib.auth import get_user_model

from utils import login


def test_login_inactive_user(db, app):
    User = get_user_model()
    user1 = User.objects.create(username='john.doe')
    user1.set_password('john.doe')
    user1.save()
    user2 = User.objects.create(username='john.doe')
    user2.set_password('john.doe')
    user2.save()

    login(app, user1)
    assert int(app.session['_auth_user_id']) in [user1.id, user2.id]
    app.get('/logout/').form.submit()
    assert '_auth_user_id' not in app.session
    user1.is_active = False
    user1.save()
    login(app, user1)
    assert int(app.session['_auth_user_id']) == user2.id
    app.get('/logout/').form.submit()
    assert '_auth_user_id' not in app.session
    user2.is_active = False
    user2.save()
    with pytest.raises(AssertionError):
        login(app, user1)
    assert '_auth_user_id' not in app.session


def test_registration_url_on_login_page(db, app):
    response = app.get('/login/?next=/whatever')
    assert 'register/?next=/whatever"' in response


def test_redirect_login_to_homepage(db, app, settings, simple_user, superuser):
    settings.A2_LOGIN_REDIRECT_AUTHENTICATED_USERS_TO_HOMEPAGE = True
    login(app, simple_user)
    response = app.get('/login/')
    assert response.status_code == 302


def test_exponential_backoff(db, app, settings):
    response = app.get('/login/')
    response.form.set('username', '')
    response.form.set('password', 'zozo')
    response = response.form.submit('login-password-submit')
    assert response.status_code == 200

    for i in range(10):
        response.form.set('username', 'zozo')
        response.form.set('password', 'zozo')
        response = response.form.submit('login-password-submit')
        assert 'too many login' not in response.content

    settings.A2_LOGIN_EXPONENTIAL_RETRY_TIMEOUT_DURATION = 1.0
    settings.A2_LOGIN_EXPONENTIAL_RETRY_TIMEOUT_MIN_DURATION = 10.0

    for i in range(10):
        response.form.set('username', 'zozo')
        response.form.set('password', 'zozo')
        response = response.form.submit('login-password-submit')
        if 1.8 ** i > 10:
            break
        assert 'too many login' not in response.content, '%s' % i
    assert 'too many login' in response.content, '%s' % i


def test_encoded_utf8_in_next_url(app, db):
    url = '/manage/roles/?search-ou=all&search-text=r%C3%A9dacteur&search-internals=on'
    response = app.get(url)
    response = response.follow()
    needle = 'next=%s' % quote(url)
    assert needle in response.content


def test_session_expire(app, simple_user, freezer):
    freezer.move_to('2018-01-01')
    # Verify session work as usual
    login(app, simple_user)
    response = app.get('/')
    assert simple_user.first_name in response
    freezer.move_to('2018-01-15')
    response = app.get('/')
    assert simple_user.first_name not in response


def test_session_remember_me_ok(app, settings, simple_user, freezer):
    settings.A2_USER_REMEMBER_ME = 3600 * 24 * 30
    freezer.move_to('2018-01-01')
    # Verify session are longer
    login(app, simple_user, remember_me=True)

    response = app.get('/')
    assert simple_user.first_name in response

    # less than 30 days, session is still alive
    freezer.move_to('2018-01-30')
    response = app.get('/')
    assert simple_user.first_name in response


def test_session_remember_me_nok(app, settings, simple_user, freezer):
    settings.A2_USER_REMEMBER_ME = 3600 * 24 * 30
    freezer.move_to('2018-01-01')
    # Verify session are longer
    login(app, simple_user, remember_me=True)

    response = app.get('/')
    assert simple_user.first_name in response

    # more than 30 days, session is dead
    freezer.move_to('2018-01-31')
    response = app.get('/')
    assert simple_user.first_name not in response
