import re

import utils


def change_email(app, user, email, mailoutbox):
    utils.login(app, user)
    l = len(mailoutbox)
    response = app.get('/accounts/change-email/')
    response.form.set('email', email)
    response.form.set('password', user.username)
    response = response.form.submit()
    assert len(mailoutbox) == l + 1
    return mailoutbox[-1]


def test_change_email(app, simple_user, user_ou1, mailoutbox):
    email = change_email(app, simple_user, user_ou1.email, mailoutbox)
    links = re.findall('https?://[^ \n]*', email.body)
    assert links
    link = links[0]
    app.get(link)
    simple_user.refresh_from_db()
    # ok it worked
    assert simple_user.email == user_ou1.email


def test_change_email_email_is_unique(app, settings, simple_user, user_ou1, mailoutbox):
    settings.A2_EMAIL_IS_UNIQUE = True
    email = change_email(app, simple_user, user_ou1.email, mailoutbox)
    links = re.findall('https?://[^ \n]*', email.body)
    assert links
    link = links[0]
    # email change is impossible as email is already taken
    assert 'password/reset' in link


def test_change_email_ou_email_is_unique(app, simple_user, user_ou1, user_ou2, mailoutbox):
    user_ou1.ou.email_is_unique = True
    user_ou1.ou.save()
    user_ou2.email = 'john.doe-ou2@example.net'
    user_ou2.save()
    email = change_email(app, simple_user, user_ou2.email, mailoutbox)
    links = re.findall('https?://[^ \n]*', email.body)
    assert links
    link = links[0]
    app.get(link)
    simple_user.refresh_from_db()
    # ok it worked for a differnt ou
    assert simple_user.email == user_ou2.email
    # now set simple_user in same ou as user_ou1
    simple_user.ou = user_ou1.ou
    simple_user.save()
    email = change_email(app, simple_user, user_ou1.email, mailoutbox)
    links = re.findall('https?://[^ \n]*', email.body)
    assert links
    link = links[0]
    # email change is impossible as email is already taken in the same ou
    assert 'password/reset' in link
