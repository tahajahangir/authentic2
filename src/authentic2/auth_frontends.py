from django.shortcuts import render
from django.utils.translation import ugettext as _, ugettext_lazy

from . import views, app_settings, utils, constants, forms


class LoginPasswordBackend(object):
    submit_name = 'login-password-submit'

    def enabled(self):
        return app_settings.A2_AUTH_PASSWORD_ENABLE

    def name(self):
        return ugettext_lazy('Password')

    def id(self):
        return 'password'

    def login(self, request, *args, **kwargs):
        context = kwargs.get('context', {})
        is_post = request.method == 'POST' and self.submit_name in request.POST
        data = request.POST if is_post else None
        form = forms.AuthenticationForm(request=request, data=data)
        if app_settings.A2_ACCEPT_EMAIL_AUTHENTICATION:
            form.fields['username'].label = _('Username or email')
        if app_settings.A2_USERNAME_LABEL:
            form.fields['username'].label = app_settings.A2_USERNAME_LABEL
        is_secure = request.is_secure
        context['submit_name'] = self.submit_name
        if is_post:
            utils.csrf_token_check(request, form)
            if form.is_valid():
                if is_secure:
                    how = 'password-on-https'
                else:
                    how = 'password'
                return utils.login(request, form.get_user(), how,
                                   service_slug=request.GET.get(constants.SERVICE_FIELD_NAME))
        context['form'] = form
        return render(request, 'authentic2/login_password_form.html', context)

    def profile(self, request, *args, **kwargs):
        return views.login_password_profile(request, *args, **kwargs)
