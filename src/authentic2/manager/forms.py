import hashlib
import smtplib
import logging

from django.utils.translation import ugettext_lazy as _, pgettext
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models.query import Q
from django.utils.text import slugify
from django.core.exceptions import ValidationError

from authentic2.compat import get_user_model
from authentic2.passwords import generate_password
from authentic2.utils import send_templated_mail
from authentic2.forms.fields import NewPasswordField, CheckPasswordField

from django_rbac.models import Operation
from django_rbac.utils import get_ou_model, get_role_model, get_permission_model
from django_rbac.backends import DjangoRBACBackend

from authentic2.forms import BaseUserForm
from authentic2.models import PasswordReset
from authentic2.utils import import_module_or_class
from authentic2.a2_rbac.utils import get_default_ou
from authentic2.utils import send_password_reset_mail, send_email_change_email
from authentic2 import app_settings as a2_app_settings

from . import fields, app_settings, utils


logger = logging.getLogger(__name__)


class CssClass(object):
    error_css_class = 'error'
    required_css_class = 'required'


class FormWithRequest(forms.Form):
    need_request = True

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(FormWithRequest, self).__init__(*args, **kwargs)


class SlugMixin(forms.ModelForm):
    def save(self, commit=True):
        instance = self.instance
        if not instance.slug:
            instance.slug = slugify(unicode(instance.name)).lstrip('_')
            qs = instance.__class__.objects.all()
            if instance.pk:
                qs = qs.exclude(pk=instance.pk)
            i = 1
            while qs.filter(slug=instance.slug).exists():
                instance.slug += str(i)
                i += 1
        if len(instance.slug) > 256:
            instance.slug = instance.slug[:252] + \
                hashlib.md5(instance.slug).hexdigest()[:4]
        return super(SlugMixin, self).save(commit=commit)


class PrefixFormMixin(object):
    def __init__(self, *args, **kwargs):
        kwargs['prefix'] = self.__class__.prefix
        super(PrefixFormMixin, self).__init__(*args, **kwargs)


class LimitQuerysetFormMixin(FormWithRequest):
    '''Limit queryset of all model choice field based on the objects
       viewable by the user.
    '''
    field_view_permisions = None

    def __init__(self, *args, **kwargs):
        super(LimitQuerysetFormMixin, self).__init__(*args, **kwargs)
        if self.request and not self.request.user.is_anonymous():
            for name, field in self.fields.iteritems():
                qs = getattr(field, 'queryset', None)
                if not qs:
                    continue
                if self.field_view_permisions \
                   and name in self.field_view_permisions:
                    perm = self.field_view_permisions[name]
                else:
                    app_label = qs.model._meta.app_label
                    model_name = qs.model._meta.model_name
                    perm = '%s.search_%s' % (app_label, model_name)
                qs = self.request.user.filter_by_perm(perm, qs)
                field.queryset = qs
                if not qs.exists():
                    # This should not happen, but could, so log it as error to find it later
                    logger.error(u'user has no search permissions on model %s with roles %s',
                                 qs.model, list(self.request.user.roles_and_parents()))


class ChooseUserForm(CssClass, forms.Form):
    user = fields.ChooseUserField(label=_('Add an user'))
    action = forms.CharField(initial='add', widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        ou = kwargs.pop('ou', None)
        super(ChooseUserForm, self).__init__(*args, **kwargs)
        # Filter user by ou if asked
        if ou:
            self.fields['user'].queryset = self.fields['user'].queryset.filter(ou=ou)


class ChooseRoleForm(CssClass, forms.Form):
    role = fields.ChooseRoleField(label=_('Add a role'))
    action = forms.CharField(initial='add', widget=forms.HiddenInput)


class UsersForm(CssClass, forms.Form):
    users = fields.ChooseUsersField(label=_('Add some users'))


class RoleForm(CssClass, forms.Form):
    role = fields.ChooseRoleField(label=_('Add a role'))


class RolesForm(CssClass, forms.Form):
    roles = fields.ChooseRolesField(label=_('Add some roles'))


class RolesForChangeForm(CssClass, forms.Form):
    roles = fields.ChooseRolesForChangeField(label=_('Add some roles'))


class ChooseUserRoleForm(CssClass, FormWithRequest, forms.Form):
    role = fields.ChooseUserRoleField(label=_('Add a role'))
    action = forms.CharField(initial='add', widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        ou = kwargs.pop('ou', None)
        super(ChooseUserRoleForm, self).__init__(*args, **kwargs)
        # Filter roles by ou if asked
        if ou:
            self.fields['role'].queryset = self.fields['role'].queryset.filter(ou=ou)


class ChoosePermissionForm(CssClass, forms.Form):
    operation = forms.ModelChoiceField(
        required=False,
        label=_('Operation'),
        queryset=Operation.objects)
    ou = forms.ModelChoiceField(
        label=_('Organizational unit'),
        queryset=get_ou_model().objects,
        required=False)
    target = forms.ModelChoiceField(
        label=_('Target object'),
        required=False,
        queryset=ContentType.objects)
    action = forms.CharField(
        initial='add',
        required=False,
        widget=forms.HiddenInput)
    permission = forms.ModelChoiceField(
        queryset=get_permission_model().objects,
        required=False,
        widget=forms.HiddenInput)


class UserEditForm(LimitQuerysetFormMixin, CssClass, BaseUserForm):
    css_class = "user-form"
    form_id = "id_user_edit_form"

    def __init__(self, *args, **kwargs):
        request = kwargs.get('request')

        super(UserEditForm, self).__init__(*args, **kwargs)
        if 'ou' in self.fields and not request.user.is_superuser:
            field = self.fields['ou']
            field.required = True
            qs = field.queryset
            if self.instance and self.instance.pk:
                perm = 'custom_user.change_user'
            else:
                perm = 'custom_user.add_user'
            qs = DjangoRBACBackend().ous_with_perm(request.user, perm)
            field.queryset = qs
            count = qs.count()
            if count == 1:
                field.initial = qs[0].pk
            if count < 2:
                field.widget.attrs['disabled'] = ''
            if self.is_bound and count == 1:
                self.data._mutable = True
                self.data[self.add_prefix('ou')] = qs[0].pk
                self.data._mutable = False

    def clean(self):
        if 'username' in self.fields or 'email' in self.fields:
            if not self.cleaned_data.get('username') and \
               not self.cleaned_data.get('email'):
                raise forms.ValidationError(
                    _('You must set a username or an email.'))

        User = get_user_model()
        if self.cleaned_data.get('email'):
            qs = User.objects.all()
            ou = getattr(self, 'ou', None)

            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
                ou = self.instance.ou

            email = self.cleaned_data['email']
            already_used = False

            if a2_app_settings.A2_EMAIL_IS_UNIQUE and qs.filter(email=email).exists():
                already_used = True

            if ou and ou.email_is_unique and qs.filter(ou=ou, email=email).exists():
                already_used = True

            if already_used:
                raise forms.ValidationError({
                    'email': _('Email already used.')
                })

    class Meta:
        model = get_user_model()
        exclude = ('is_staff', 'groups', 'user_permissions', 'last_login',
                   'date_joined', 'password')


class UserChangePasswordForm(CssClass, forms.ModelForm):
    error_messages = {
        'password_mismatch': _("The two password fields didn't match."),
    }
    notification_template_prefix = \
        'authentic2/manager/change-password-notification'

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['password_mismatch'],
                code='password_mismatch',
            )
        return password2

    def clean(self):
        super(UserChangePasswordForm, self).clean()
        if not self.cleaned_data.get('generate_password') \
                and not self.cleaned_data.get('password1') \
                and not self.cleaned_data.get('send_password_reset'):
            raise forms.ValidationError(
                _('You must choose password generation or type a new'
                  '  one or send a password reset mail'))
        if (self.instance and self.instance.pk and not self.instance.email and
            (self.cleaned_data.get('send_mail')
             or self.cleaned_data.get('generate_password'
             or self.cleaned_data.get('send_password_reset')))):
            raise forms.ValidationError(
                _('User does not have a mail, we cannot send the '
                  'informations to him.'))

    def save(self, commit=True):
        user = super(UserChangePasswordForm, self).save(commit=False)
        new_password = None
        if self.cleaned_data.get('generate_password'):
            new_password = generate_password()
            self.cleaned_data['send_mail'] = True
        elif self.cleaned_data.get('password1'):
            new_password = self.cleaned_data["password1"]

        if new_password:
            user.set_password(new_password)

        if commit:
            user.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()

        if not self.cleaned_data.get('send_password_reset'):
            if self.cleaned_data['send_mail']:
                send_templated_mail(
                    user,
                    self.notification_template_prefix,
                    context={'new_password': new_password, 'user': user})
        return user

    generate_password = forms.BooleanField(
        initial=False,
        label=_('Generate new password'),
        required=False)
    password1 = NewPasswordField(
        label=_("Password"),
        required=False)
    password2 = CheckPasswordField(
        label=_("Confirmation"),
        required=False)
    send_mail = forms.BooleanField(
        initial=True,
        label=_('Send informations to user'),
        required=False)

    class Meta:
        model = get_user_model()
        fields = ()


class UserAddForm(UserChangePasswordForm, UserEditForm):
    css_class = "user-form"
    form_id = "id_user_add_form"

    notification_template_prefix = \
        'authentic2/manager/new-account-notification'
    reset_password_at_next_login = forms.BooleanField(
        initial=False,
        label=_('Ask for password reset on next login'),
        required=False)

    send_password_reset = forms.BooleanField(
        initial=False,
        label=_('Send mail to user to make it choose a password'),
        required=False)

    def __init__(self, *args, **kwargs):
        self.ou = kwargs.pop('ou', None)
        super(UserAddForm, self).__init__(*args, **kwargs)

    def clean(self):
        super(UserAddForm, self).clean()
        User = get_user_model()

        if not self.cleaned_data.get('username') and \
           not self.cleaned_data.get('email'):
            raise forms.ValidationError(
                _('You must set a username or an email.'))

    def save(self, commit=True):
        self.instance.ou = self.ou
        user = super(UserAddForm, self).save(commit=commit)
        if self.cleaned_data.get('reset_password_at_next_login'):
            if commit:
                PasswordReset.objects.get_or_create(user=user)
            else:
                old_save = user.save

                def save(*args, **kwargs):
                    old_save(*args, **kwargs)
                    PasswordReset.objects.get_or_create(user=user)
                user.save = save
        if self.cleaned_data.get('send_password_reset'):
            try:
                send_password_reset_mail(
                    user,
                    template_names=['authentic2/manager/user_create_registration_email',
                                    'authentic2/password_reset'],
                    request=self.request,
                    next_url='/accounts/',
                    context={
                        'user': user,
                    })
            except smtplib.SMTPException, e:
                logger.error(u'registration mail could not be sent to user %s created through '
                             u'manager: %s', user, e)
        return user

    class Meta:
        model = get_user_model()
        fields = '__all__'
        exclude = ('ou',)


class ServiceRoleSearchForm(CssClass, PrefixFormMixin, FormWithRequest):
    prefix = 'search'

    text = forms.CharField(
        label=_('Name'),
        required=False)
    internals = forms.BooleanField(
        initial=False,
        label=_('Show internal roles'),
        required=False)

    def __init__(self, *args, **kwargs):
        super(ServiceRoleSearchForm, self).__init__(*args, **kwargs)
        if app_settings.SHOW_INTERNAL_ROLES:
            del self.fields['internals']

    def filter(self, qs):
        if hasattr(super(ServiceRoleSearchForm, self), 'filter'):
            qs = super(ServiceRoleSearchForm, self).filter(qs)
        if self.cleaned_data.get('text'):
            qs = qs.filter(name__icontains=self.cleaned_data['text'])
        if not app_settings.SHOW_INTERNAL_ROLES and not self.cleaned_data.get('internals'):
            qs = qs.exclude(slug__startswith='_a2')
        return qs


class HideOUFieldMixin(object):
    def __init__(self, *args, **kwargs):
        super(HideOUFieldMixin, self).__init__(*args, **kwargs)
        if utils.get_ou_count() < 2:
            del self.fields['ou']

    def save(self, *args, **kwargs):
        if 'ou' not in self.fields:
            self.instance.ou = get_default_ou()
        return super(HideOUFieldMixin, self).save(*args, **kwargs)


class OUSearchForm(FormWithRequest):
    ou_permission = None
    queryset = None

    ou = forms.ChoiceField(label=_('Organizational unit'), required=False)

    def __init__(self, *args, **kwargs):
        # if there are many OUs:
        # - show all if show_all_ou is True and user has ou_permission over all OUs or more than
        #   one,
        # - show searchable OUs
        # - show none if user has ou_permission over all OUs
        # - when no choice is made,
        #   - show all ou is show_all_ou is True (including None if user has ou_permission over all
        #   OUs)
        #   - else show none OU
        # - when a choice is made apply it
        # if there is one OU:
        # - hide ou field
        all_ou_label = kwargs.pop('all_ou_label', pgettext('organizational unit', 'All'))
        self.queryset = kwargs.pop('queryset', None)
        self.show_all_ou = kwargs.pop('show_all_ou', True)
        request = kwargs['request']
        self.ou_count = utils.get_ou_count()

        if self.ou_count > 1:
            self.search_all_ous = request.user.has_perm(self.ou_permission)
            if 'ou_queryset' in kwargs:
                self.ou_qs = kwargs.pop('ou_queryset')
            elif self.search_all_ous:
                self.ou_qs = get_ou_model().objects.all()
            else:
                self.ou_qs = request.user.ous_with_perm(self.ou_permission)

            if self.queryset:
                # we were passed an explicit list of objects linked to OUs by a field named 'ou',
                # get possible OUs from this list
                related_query_name = self.queryset.model._meta.get_field('ou').related_query_name()
                objects_ou_qs = get_ou_model().objects.filter(
                    **{"%s__in" % related_query_name: self.queryset}).distinct()
                # to combine queryset with distinct, each queryset must have the distinct flag
                self.ou_qs = (self.ou_qs.distinct() | objects_ou_qs)

            # even if default ordering is by name on the model, we are not sure it's kept after the
            # ORing in the previous if condition, so we sort it again.
            self.ou_qs = self.ou_qs.order_by('name')

            # build choice list
            choices = []
            if self.show_all_ou and (len(self.ou_qs) > 1 or self.search_all_ous):
                choices.append(('all', all_ou_label))
            for ou in self.ou_qs:
                choices.append((str(ou.pk), unicode(ou)))
            if self.search_all_ous:
                choices.append(('none', pgettext('organizational unit', 'None')))

            # if user does not have ou_permission over all OUs, select user OU as default selected
            # OU we must modify data as the form must always be valid
            ou_key = self.add_prefix('ou')
            data = kwargs.setdefault('data', {}).copy()
            kwargs['data'] = data
            if ou_key not in data:
                initial_ou = kwargs.get('initial', {}).get('ou')
                if initial_ou in [str(ou.pk) for ou in self.ou_qs]:
                    data[ou_key] = initial_ou
                elif self.show_all_ou and (self.search_all_ous or len(self.ou_qs) > 1):
                    data[ou_key] = 'all'
                elif request.user.ou in self.ou_qs:
                    data[ou_key] = str(request.user.ou.pk)
                else:
                    data[ou_key] = str(self.ou_qs[0].pk)

        super(OUSearchForm, self).__init__(*args, **kwargs)

        # modify choices after initialization
        if self.ou_count > 1:
            self.fields['ou'].choices = choices

        # if there is only one OU, we remove the field
        # if there is only one choice, we disable the field
        if self.ou_count < 2:
            del self.fields['ou']
        elif len(choices) < 2:
            self.fields['ou'].widget.attrs['disabled'] = ''

    def filter_no_ou(self, qs):
        if self.ou_count > 1:
            if self.show_all_ou:
                if self.search_all_ous:
                    return qs
                else:
                    return qs.filter(ou__in=self.ou_qs)
            else:
                qs = qs.none()
        return qs

    def clean(self):
        ou = self.cleaned_data.get('ou')
        self.cleaned_data['ou_filter'] = ou
        try:
            ou_pk = int(ou)
        except (TypeError, ValueError):
            self.cleaned_data['ou'] = None
        else:
            for ou in self.ou_qs:
                if ou.pk == ou_pk:
                    self.cleaned_data['ou'] = ou
                    break
            else:
                self.cleaned_data['ou'] = None
        return self.cleaned_data

    def filter_by_ou(self, qs):
        if self.cleaned_data.get('ou_filter'):
            ou_filter = self.cleaned_data['ou_filter']
            ou = self.cleaned_data['ou']
            if ou_filter == 'all':
                qs = self.filter_no_ou(qs)
            elif ou_filter == 'none':
                qs = qs.filter(ou__isnull=True)
            elif ou:
                qs = qs.filter(ou=ou)
        else:
            qs = self.filter_no_ou(qs)
        return qs

    def filter(self, qs):
        if hasattr(super(OUSearchForm, self), 'filter'):
            qs = super(OUSearchForm, self).filter(qs)
        qs = self.filter_by_ou(qs)
        return qs


class RoleSearchForm(ServiceRoleSearchForm, OUSearchForm):
    ou_permission = 'a2_rbac.search_role'


class UserRoleSearchForm(OUSearchForm, ServiceRoleSearchForm):
    ou_permission = 'a2_rbac.change_role'

    def __init__(self, *args, **kwargs):
        request = kwargs['request']
        user = kwargs.pop('user')
        role_members_from_ou = kwargs.pop('role_members_from_ou')

        if role_members_from_ou:
            assert user
            # limit ou to target user ou
            ou_qs = request.user.ous_with_perm(self.ou_permission).order_by('name')
            if user.ou_id:
                ou_qs = ou_qs.filter(id=user.ou_id)
            else:
                ou_qs = ou_qs.none()
            kwargs['ou_queryset'] = ou_qs
        super(UserRoleSearchForm, self).__init__(*args, **kwargs)

    def filter_no_ou(self, qs):
        return qs


class UserSearchForm(OUSearchForm, CssClass, PrefixFormMixin, FormWithRequest):
    ou_permission = 'custom_user.search_user'
    prefix = 'search'

    text = forms.CharField(
        label=_('Free text'),
        required=False)

    def __init__(self, *args, **kwargs):
        self.minimum_chars = kwargs.pop('minimum_chars', 0)
        super(UserSearchForm, self).__init__(*args, **kwargs)

    def not_enough_chars(self):
        text = self.cleaned_data.get('text')
        return self.minimum_chars and (not text or len(text) < self.minimum_chars)

    def enough_chars(self):
        text = self.cleaned_data.get('text')
        return text and len(text) >= self.minimum_chars

    def filter(self, qs):
        qs = super(UserSearchForm, self).filter(qs)
        if self.enough_chars():
            qs = utils.filter_user(qs, self.cleaned_data['text'])
        elif self.not_enough_chars():
            qs = qs.none()
        return qs


class NameSearchForm(CssClass, PrefixFormMixin, FormWithRequest):
    prefix = 'search'

    text = forms.CharField(
        label=_('Name'),
        required=False)

    def filter(self, qs):
        if self.cleaned_data.get('text'):
            qs = qs.filter(name__icontains=self.cleaned_data['text'])
        return qs


class RoleEditForm(SlugMixin, HideOUFieldMixin, LimitQuerysetFormMixin, CssClass,
                   forms.ModelForm):
    ou = forms.ModelChoiceField(queryset=get_ou_model().objects,
                                required=True, label=_('Organizational unit'))

    def clean_name(self):
        qs = get_role_model().objects.all()
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        ou = self.cleaned_data.get('ou')
        # Test unicity of name for an OU and globally if no OU is present
        name = self.cleaned_data.get('name')
        if name and ou:
            query = Q(name=name) & (Q(ou__isnull=True) | Q(ou=ou))
            if qs.filter(query).exists():
                raise ValidationError(
                    {'name': _('This name is not unique over this organizational unit.')})
        return name

    class Meta:
        model = get_role_model()
        fields = ('name', 'ou', 'description')


class OUEditForm(SlugMixin, CssClass, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(OUEditForm, self).__init__(*args, **kwargs)
        self.fields['name'].label = _('label').title()

    class Meta:
        model = get_ou_model()
        fields = ('name', 'default', 'username_is_unique', 'email_is_unique', 'validate_emails')


def get_role_form_class():
    if app_settings.ROLE_FORM_CLASS:
        return import_module_or_class(app_settings.ROLE_FORM_CLASS)
    return RoleEditForm


# we need a model form so that we can use a BaseEditView, a simple Form
# would not work
class UserChangeEmailForm(CssClass, FormWithRequest, forms.ModelForm):
    new_email = forms.EmailField(label=_('Email'))

    def __init__(self, *args, **kwargs):
        initial = kwargs.setdefault('initial', {})
        instance = kwargs.get('instance')
        if instance:
            initial['new_email'] = instance.email
        super(UserChangeEmailForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        new_email = self.cleaned_data['new_email']
        send_email_change_email(
            self.instance,
            new_email,
            request=self.request,
            template_names=['authentic2/manager/user_change_email_notification'])
        return self.instance

    class Meta:
        fields = ()
