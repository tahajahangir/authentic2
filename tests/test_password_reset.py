from django.core.urlresolvers import reverse

import utils


def test_send_password_reset_email(app, simple_user, mailoutbox):
    from authentic2.utils import send_password_reset_mail
    assert len(mailoutbox) == 0
    send_password_reset_mail(
        simple_user,
        legacy_subject_templates=['registration/password_reset_subject.txt'],
        legacy_body_templates=['registration/password_reset_email.html'],
        context={
            'base_url': 'http://testserver',
        })
    assert len(mailoutbox) == 1
    url = utils.get_link_from_mail(mailoutbox[0])
    relative_url = url.split('testserver')[1]
    resp = app.get(relative_url, status=200)
    resp.form.set('new_password1', '1234==aA')
    resp.form.set('new_password2', '1234==aA')
    resp = resp.form.submit().follow()
    assert str(app.session['_auth_user_id']) == str(simple_user.pk)


def test_view(app, simple_user, mailoutbox):
    url = reverse('password_reset') + '?next=/moncul/'
    resp = app.get(url, status=200)
    resp.form.set('email', simple_user.email)
    assert len(mailoutbox) == 0
    resp = resp.form.submit()
    assert resp['Location'].endswith('/moncul/')
    assert len(mailoutbox) == 1
    url = utils.get_link_from_mail(mailoutbox[0])
    relative_url = url.split('testserver')[1]
    resp = app.get(relative_url, status=200)
    resp.form.set('new_password1', '1234==aA')
    resp.form.set('new_password2', '1234==aA')
    resp = resp.form.submit()
    # verify user is logged
    assert str(app.session['_auth_user_id']) == str(simple_user.pk)
    # verify next_url was kept
    assert resp['Location'].endswith('/moncul/')


def test_user_filter(app, simple_user, mailoutbox, settings):
    settings.A2_USER_FILTER = {'username': 'xxx'}  # will not match simple_user

    url = reverse('password_reset') + '?next=/moncul/'
    resp = app.get(url, status=200)
    resp.form.set('email', simple_user.email)
    assert len(mailoutbox) == 0
    resp = resp.form.submit()
    assert resp['Location'].endswith('/moncul/')
    assert len(mailoutbox) == 0


def test_user_exclude(app, simple_user, mailoutbox, settings):
    settings.A2_USER_EXCLUDE = {'username': simple_user.username}  # will not match simple_user

    url = reverse('password_reset') + '?next=/moncul/'
    resp = app.get(url, status=200)
    resp.form.set('email', simple_user.email)
    assert len(mailoutbox) == 0
    resp = resp.form.submit()
    assert resp['Location'].endswith('/moncul/')
    assert len(mailoutbox) == 0
