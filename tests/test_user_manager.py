from django.core.urlresolvers import reverse

from authentic2.a2_rbac.utils import get_default_ou
from utils import login, get_link_from_mail


def test_manager_user_change_email(app, superuser_or_admin, simple_user, mailoutbox):
    ou = get_default_ou()
    ou.validate_emails = True
    ou.save()

    response = login(app, superuser_or_admin,
                     reverse('a2-manager-user-by-uuid-detail',
                             kwargs={'slug': unicode(simple_user.uuid)}))
    assert 'Change user email' in response.content
    # cannot click it's a submit button :/
    response = app.get(reverse('a2-manager-user-by-uuid-change-email',
                               kwargs={'slug': unicode(simple_user.uuid)}))
    response.form.set('email', 'john.doe@example.com')
    assert len(mailoutbox) == 0
    response = response.form.submit().follow()
    assert 'A mail was sent to john.doe@example.com to verify it.' in response.content
    assert 'Change user email' in response.content
    # cannot click it's a submit button :/
    assert len(mailoutbox) == 1
    # logout
    app.session.flush()

    link = get_link_from_mail(mailoutbox[0])
    response = app.get(link).maybe_follow()
    assert (
        'your request for changing your email for john.doe@example.com is successful'
        in response.content)
    simple_user.refresh_from_db()
    assert simple_user.email == 'john.doe@example.com'
