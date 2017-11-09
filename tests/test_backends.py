from django.contrib.auth import authenticate
from authentic2.backends import is_user_authenticable


def test_user_filters(settings, db, simple_user, user_ou1, ou1):
    assert authenticate(username=simple_user.username, password=simple_user.username)
    assert is_user_authenticable(simple_user)
    assert is_user_authenticable(user_ou1)
    assert authenticate(username=user_ou1.username, password=user_ou1.username)
    settings.A2_USER_FILTER = {'ou__slug': 'ou1'}
    assert not authenticate(username=simple_user.username, password=simple_user.username)
    assert authenticate(username=user_ou1.username, password=user_ou1.username)
    assert not is_user_authenticable(simple_user)
    assert is_user_authenticable(user_ou1)
    settings.A2_USER_EXCLUDE = {'ou__slug': 'ou1'}
    assert not authenticate(username=simple_user.username, password=simple_user.username)
    assert not authenticate(username=user_ou1.username, password=user_ou1.username)
    assert not is_user_authenticable(simple_user)
    assert not is_user_authenticable(user_ou1)
    settings.A2_USER_FILTER = {}
    assert authenticate(username=simple_user.username, password=simple_user.username)
    assert not authenticate(username=user_ou1.username, password=user_ou1.username)
    assert is_user_authenticable(simple_user)
    assert not is_user_authenticable(user_ou1)
