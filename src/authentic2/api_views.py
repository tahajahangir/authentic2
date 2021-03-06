'''Views for Authentic2 API'''
import logging
import smtplib

from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned
from django.utils.translation import ugettext as _
from django.views.decorators.vary import vary_on_headers
from django.views.decorators.cache import cache_control
from django.shortcuts import get_object_or_404

from django_rbac.utils import get_ou_model, get_role_model

from rest_framework import serializers, pagination
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.routers import SimpleRouter
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
from rest_framework.fields import CreateOnlyDefault
from rest_framework.decorators import list_route, detail_route
from rest_framework.authentication import SessionAuthentication

from django_filters.rest_framework import FilterSet

from .passwords import get_password_checker
from .custom_user.models import User
from . import utils, decorators, attribute_kinds, app_settings, hooks
from .models import Attribute, PasswordReset, Service
from .a2_rbac.utils import get_default_ou


class HookMixin(object):
    def get_serializer(self, *args, **kwargs):
        serializer = super(HookMixin, self).get_serializer(*args, **kwargs)
        # if the serializer is a ListSerializer, we modify the child
        if hasattr(serializer, 'child'):
            hooks.call_hooks('api_modify_serializer', self, serializer.child)
        else:
            hooks.call_hooks('api_modify_serializer', self, serializer)
        return serializer

    def get_object(self):
        hooks.call_hooks('api_modify_view_before_get_object', self)
        return super(HookMixin, self).get_object()


class DjangoPermission(permissions.BasePermission):
    def __init__(self, perm):
        self.perm = perm

    def has_permission(self, request, view):
        return request.user.has_perm(self.perm)

    def has_object_permission(self, request, view, obj):
        return request.user.has_perm(self.perm, obj=obj)

    def __call__(self):
        return self


class ExceptionHandlerMixin(object):
    def handle_exception(self, exc):
        if hasattr(exc, 'detail'):
            exc.detail = {
                'result': 0,
                'errors': exc.detail,
            }
            return super(ExceptionHandlerMixin, self).handle_exception(exc)
        else:
            response = super(ExceptionHandlerMixin, self).handle_exception(exc)
            response.data = {
                'result': 0,
                'errors': response.data,
            }
            return response


class RegistrationSerializer(serializers.Serializer):
    '''Register RPC payload'''
    email = serializers.EmailField(
        required=False, allow_blank=True)
    ou = serializers.SlugRelatedField(
        queryset=get_ou_model().objects.all(),
        slug_field='slug',
        default=get_default_ou,
        required=False, allow_null=True)
    username = serializers.CharField(
        required=False, allow_blank=True)
    first_name = serializers.CharField(
        required=False, allow_blank=True, default='')
    last_name = serializers.CharField(
        required=False, allow_blank=True, default='')
    password = serializers.CharField(
        required=False, allow_null=True)
    no_email_validation = serializers.BooleanField(
        required=False)
    return_url = serializers.URLField(required=False, allow_blank=True)

    def validate(self, data):
        request = self.context.get('request')
        ou = data.get('ou')
        if request:
            perm = 'custom_user.add_user'
            if ou:
                authorized = request.user.has_ou_perm(perm, data['ou'])
            else:
                authorized = request.user.has_perm(perm)
            if not authorized:
                raise serializers.ValidationError(_('you are not authorized '
                                                    'to create users in '
                                                    'this ou'))
        User = get_user_model()
        if ou:
            if ou.email_is_unique and \
                    User.objects.filter(ou=ou, email__iexact=data['email']).exists():
                raise serializers.ValidationError(
                    _('You already have an account'))
            if ou.username_is_unique and not \
                    'username' in data:
                raise serializers.ValidationError(
                    _('Username is required in this ou'))
            if ou.username_is_unique and User.objects.filter(
                    ou=data['ou'], username=data['username']).exists():
                raise serializers.ValidationError(_('You already have an account'))
        return data


class RpcMixin(object):
    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            response, response_status = self.rpc(request, serializer)
            return Response(response, response_status)
        else:
            response = {'result': 0, 'errors': serializer.errors}
            return Response(response, status.HTTP_400_BAD_REQUEST)


class BaseRpcView(ExceptionHandlerMixin, RpcMixin, GenericAPIView):
    pass


class Register(BaseRpcView):
    '''Register the given email, send a mail to the user and return a
       validation token.

       A mail will be sent to the user to validate its email. On
       validation of the mail the user will be logged and redirected to
       `{return_url}?token={token}`. It's the durty of the requesting
       service to finish the registration process on its side.

       If email is unique and an account already exist the requesting
       must enter in a process of registration through SSO, i.e. ask for
       authentication of the user and then finish the registration
       process for the received identity.
    '''
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = RegistrationSerializer

    def rpc(self, request, serializer):
        validated_data = serializer.validated_data
        if not request.user.has_ou_perm('custom_user.add_user', validated_data['ou']):
            raise PermissionDenied('You do not have permission to create users in ou %s' %
                                   validated_data['ou'].slug)
        email = validated_data.get('email')
        registration_data = {}
        for field in ('first_name', 'last_name', 'password', 'username'):
            if field in validated_data:
                if isinstance(validated_data[field], models.Model):
                    registration_data[field] = validated_data[field].pk
                else:
                    registration_data[field] = validated_data[field]
        ctx = {
            'registration_data': registration_data,
        }

        token = None
        final_return_url = None
        if validated_data.get('return_url'):
            token = utils.get_hex_uuid()[:16]
            final_return_url = utils.make_url(validated_data['return_url'],
                                              params={'token': token})
        if email and not validated_data.get('no_email_validation'):

            registration_template = ['authentic2/activation_email']
            if validated_data['ou']:
                registration_template.insert(0, 'authentic2/activation_email_%s' %
                                             validated_data['ou'].slug)

            try:
                utils.send_registration_mail(self.request, email,
                                             template_names=registration_template,
                                             next_url=final_return_url,
                                             ou=validated_data['ou'],
                                             context=ctx,
                                             **registration_data)
            except smtplib.SMTPException, e:
                response = {
                    'result': 0,
                    'errors': {
                        '__all__': ['Mail sending failed']
                    },
                    'exception': unicode(e),
                }
                response_status = status.HTTP_503_SERVICE_UNAVAILABLE
            else:
                response = {
                    'result': 1,
                }
                if token:
                    response['token'] = token
                response_status = status.HTTP_202_ACCEPTED
        else:
            username = validated_data.get('username')
            first_name = validated_data.get('first_name')
            last_name = validated_data.get('last_name')
            password = validated_data.get('password')
            ou = validated_data.get('ou')
            if not email and \
               not username and \
               not (first_name and last_name):
                response = {
                    'result': 0,
                    'errors': {
                        '__all__': ['You must set at least a username, an email or '
                                    'a first name and a last name']
                    },
                }
                response_status = status.HTTP_400_BAD_REQUEST
            else:
                new_user = User(email=email, username=username, ou=ou, first_name=first_name,
                                last_name=last_name)
                if password:
                    new_user.set_password(password)
                new_user.save()
                validated_data['uuid'] = new_user.uuid
                response = {
                    'result': 1,
                    'user': BaseUserSerializer(new_user).data,
                    'token': token,
                }
                if email:
                    response['validation_url'] = utils.build_activation_url(
                        request, email, next_url=final_return_url, ou=ou, **registration_data)
                if token:
                    response['token'] = token
                response_status = status.HTTP_201_CREATED
        return response, response_status

register = Register.as_view()


class PasswordChangeSerializer(serializers.Serializer):
    '''Register RPC payload'''
    email = serializers.EmailField()
    ou = serializers.SlugRelatedField(
        queryset=get_ou_model().objects.all(),
        slug_field='slug',
        required=False, allow_null=True)
    old_password = serializers.CharField(
        required=True, allow_null=True)
    new_password = serializers.CharField(
        required=True, allow_null=True)

    def validate(self, data):
        User = get_user_model()
        qs = User.objects.filter(email=data['email'])
        if data['ou']:
            qs = qs.filter(ou=data['ou'])
        try:
            self.user = qs.get()
        except User.DoesNotExist:
            raise serializers.ValidationError('no user found')
        except MultipleObjectsReturned:
            raise serializers.ValidationError('more than one user have this email')
        if not self.user.check_password(data['old_password']):
            raise serializers.ValidationError('old_password is invalid')
        return data


class PasswordChange(BaseRpcView):
    permission_classes = (DjangoPermission('custom_user.change_user'),)
    serializer_class = PasswordChangeSerializer

    def rpc(self, request, serializer):
        serializer.user.set_password(serializer.validated_data['new_password'])
        serializer.user.save()
        return {'result': 1}, status.HTTP_200_OK

password_change = PasswordChange.as_view()


@vary_on_headers('Cookie', 'Origin', 'Referer')
@cache_control(private=True, max_age=60)
@decorators.json
def user(request):
    if request.user.is_anonymous():
        return {}
    return request.user.to_json()


def attributes_hash(attributes):
    attributes = sorted(attributes, key=lambda at: at.name)
    return hash(tuple((at.name, at.required) for at in attributes))


class BaseUserSerializer(serializers.ModelSerializer):
    ou = serializers.SlugRelatedField(
        queryset=get_ou_model().objects.all(),
        slug_field='slug',
        required=False, default=get_default_ou)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)
    send_registration_email = serializers.BooleanField(write_only=True, required=False,
                                                       default=False)
    send_registration_email_next_url = serializers.URLField(write_only=True, required=False)
    password = serializers.CharField(max_length=128,
                                     default=CreateOnlyDefault(utils.generate_password),
                                     required=False)
    force_password_reset = serializers.BooleanField(write_only=True, required=False, default=False)

    def __init__(self, *args, **kwargs):
        super(BaseUserSerializer, self).__init__(*args, **kwargs)

        for at in Attribute.objects.all():
            if at.name in self.fields:
                self.fields[at.name].required = at.required
            else:
                kind = attribute_kinds.get_kind(at.kind)
                field_class = kind['rest_framework_field_class']
                kwargs = kind.get('rest_framework_field_kwargs') or {}
                kwargs.update({
                    'source': 'attributes.%s' % at.name,
                    'required': at.required,
                })
                if not at.required:
                    # setting an attribute to null will delete it
                    # NullBooleanField and BooleanField does not support allow_null
                    if field_class is serializers.BooleanField:
                        field_class = serializers.NullBooleanField
                    elif field_class is not serializers.NullBooleanField:
                        kwargs['allow_null'] = True
                    # if not stated otherwise by the definition of the kind, string alike fields
                    # accept blank values when not required
                    if (issubclass(field_class, serializers.CharField) and 'allow_blank' not in
                            kwargs):
                        kwargs['allow_blank'] = True
                self.fields[at.name] = field_class(**kwargs)
        for key in self.fields:
            if key in app_settings.A2_REQUIRED_FIELDS:
                self.fields[key].required = True

        # A2_API_USERS_REQUIRED_FIELDS override all other sources of requiredness
        if app_settings.A2_API_USERS_REQUIRED_FIELDS:
            for key in self.fields:
                self.fields[key].required = key in app_settings.A2_API_USERS_REQUIRED_FIELDS

    def check_perm(self, perm, ou):
        self.context['view'].check_perm(perm, ou)

    def create(self, validated_data):
        original_data = validated_data.copy()
        send_registration_email = validated_data.pop('send_registration_email', False)
        send_registration_email_next_url = validated_data.pop('send_registration_email_next_url',
                                                              None)
        force_password_reset = validated_data.pop('force_password_reset', False)

        attributes = validated_data.pop('attributes', {})
        self.check_perm('custom_user.add_user', validated_data.get('ou'))
        instance = super(BaseUserSerializer, self).create(validated_data)
        for key, value in attributes.iteritems():
            setattr(instance.attributes, key, value)
        if 'password' in validated_data:
            instance.set_password(validated_data['password'])
            instance.save()
        if force_password_reset:
            PasswordReset.objects.get_or_create(user=instance)
        if send_registration_email and validated_data.get('email'):
            try:
                utils.send_password_reset_mail(
                    instance,
                    template_names=['authentic2/api_user_create_registration_email',
                                    'authentic2/password_reset'],
                    request=self.context['request'],
                    next_url=send_registration_email_next_url,
                    context={
                        'data': original_data,
                    })
            except smtplib.SMTPException, e:
                logging.getLogger(__name__).error(u'registration mail could not be sent to user %s '
                                                  'created through API: %s', instance, e)
        return instance

    def update(self, instance, validated_data):
        force_password_reset = validated_data.pop('force_password_reset', False)
        # Remove unused fields
        validated_data.pop('send_registration_email', False)
        validated_data.pop('send_registration_email_next_url', None)
        attributes = validated_data.pop('attributes', {})
        # Double check: to move an user from one ou into another you must be administrator of both
        self.check_perm('custom_user.change_user', instance.ou)
        if 'ou' in validated_data:
            self.check_perm('custom_user.change_user', validated_data.get('ou'))
        super(BaseUserSerializer, self).update(instance, validated_data)
        for key, value in attributes.iteritems():
            setattr(instance.attributes, key, value)
        if 'password' in validated_data:
            instance.set_password(validated_data['password'])
            instance.save()
        if force_password_reset:
            PasswordReset.objects.get_or_create(user=instance)
        return instance

    def validate(self, data):
        User = get_user_model()
        qs = User.objects.all()

        ou = None

        if self.instance:
            ou = self.instance.ou
        if 'ou' in data and not ou:
            ou = data['ou']

        already_used = False
        if data.get('email'):
            if app_settings.A2_EMAIL_IS_UNIQUE and qs.filter(email=data['email']).exists():
                already_used = True
            if ou and ou.email_is_unique and qs.filter(ou=ou, email=data['email']).exists():
                already_used = True

        if already_used:
            raise serializers.ValidationError({
                'email': 'email already used',
            })
        return data

    class Meta:
        model = get_user_model()
        extra_kwargs = {
            'uuid': {
                'read_only': False,
                'required': False,
            }
        }
        exclude = ('date_joined', 'user_permissions', 'groups', 'last_login')


class RoleSerializer(serializers.ModelSerializer):
    ou = serializers.SlugRelatedField(
        many=False,
        required=False,
        default=CreateOnlyDefault(get_default_ou),
        queryset=get_ou_model().objects.all(),
        slug_field='slug')

    @property
    def user(self):
        return self.context['request'].user

    def __init__(self, instance=None, **kwargs):
        super(RoleSerializer, self).__init__(instance, **kwargs)
        if self.instance:
            self.fields['ou'].read_only = True

    def create(self, validated_data):
        ou = validated_data.get('ou')
        # Creating roles also means being allowed to within the OU:
        if not self.user.has_ou_perm('a2_rbac.add_role', ou):
            raise PermissionDenied(u'User %s can\'t create role in OU %s' % (self.user, ou))
        return super(RoleSerializer, self).create(validated_data)

    def update(self, instance, validated_data):
        # Check role-updating permissions:
        if not self.user.has_perm('a2_rbac.change_role', obj=instance):
            raise PermissionDenied(u'User %s can\'t change role %s' % (self.user, instance))
        super(RoleSerializer, self).update(instance, validated_data)
        return instance

    def partial_update(self, instance, validated_data):
        # Check role-updating permissions:
        if not self.user.has_perm('a2_rbac.change_role', obj=instance):
            raise PermissionDenied(u'User %s can\'t change role %s' % (self.user, instance))
        super(RoleSerializer, self).partial_update(instance, validated_data)
        return instance

    class Meta:
        model = get_role_model()
        fields = ('uuid', 'name', 'slug', 'ou',)
        extra_kwargs = {'uuid': {'read_only': True}}


class UsersFilter(FilterSet):
    class Meta:
        model = get_user_model()
        fields = {
            'username': [
                'exact',
                'iexact'
            ],
            'first_name': [
                'exact',
                'iexact',
                'icontains',
                'gte',
                'lte',
                'gt',
                'lt',
            ],
            'last_name': [
                'exact',
                'iexact',
                'icontains',
                'gte',
                'lte',
                'gt',
                'lt',
            ],
            'modified': [
                'gte',
                'lte',
                'gt',
                'lt',
            ],
            'email': [
                'exact',
                'iexact',
            ],
            'ou__slug': [
                'exact',
            ],
        }


class ChangeEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class UsersAPI(HookMixin, ExceptionHandlerMixin, ModelViewSet):
    ordering_fields = ['username', 'first_name', 'last_name', 'modified', 'date_joined']
    lookup_field = 'uuid'
    serializer_class = BaseUserSerializer
    filter_class = UsersFilter
    pagination_class = pagination.CursorPagination
    ordering = ['modified', 'id']

    def get_queryset(self):
        User = get_user_model()
        qs = User.objects.all()
        if self.request.method == 'GET':
            qs = qs.prefetch_related('attribute_values', 'attribute_values__attribute')
        qs = self.request.user.filter_by_perm(['custom_user.view_user'], qs)
        # filter users authorized for a specified service
        if 'service-slug' in self.request.GET and 'service-ou' in self.request.GET:
            service_slug = self.request.GET['service-slug']
            service_ou = self.request.GET['service-ou']
            service = Service.objects.filter(slug=service_slug, ou__slug=service_ou).prefetch_related('authorized_roles').first()
            if service and service.authorized_roles.all():
                qs = qs.filter(roles__in=service.authorized_roles.children())
                qs = qs.distinct()
        new_qs = hooks.call_hooks_first_result('api_modify_queryset', self, qs)
        if new_qs is not None:
            return new_qs
        return qs

    # only do partial updates
    def put(self, request, *args, **kwargs):
        return self.patch(request, *args, **kwargs)

    def check_perm(self, perm, ou):
        if ou:
            if not self.request.user.has_ou_perm(perm, ou):
                raise PermissionDenied(u'You do not have permission %s in %s' % (perm, ou))
        else:
            if not self.request.user.has_perm(perm):
                raise PermissionDenied(u'You do not have permission %s' % perm)

    def perform_destroy(self, instance):
        self.check_perm('custom_user.delete_user', instance.ou)
        super(UsersAPI, self).perform_destroy(instance)

    class SynchronizationSerializer(serializers.Serializer):
        known_uuids = serializers.ListField(child=serializers.CharField())

    def check_uuids(self, uuids):
        User = get_user_model()
        known_uuids = User.objects.filter(uuid__in=uuids).values_list('uuid', flat=True)
        return set(uuids) - set(known_uuids)

    @list_route(methods=['post'], permission_classes=(DjangoPermission('custom_user.search_user'),))
    def synchronization(self, request):
        serializer = self.SynchronizationSerializer(data=request.data)
        if not serializer.is_valid():
            response = {
                'result': 0,
                'errors': serializer.errors
            }
            return Response(response, status.HTTP_400_BAD_REQUEST)
        hooks.call_hooks('api_modify_serializer_after_validation', self, serializer)
        unknown_uuids = self.check_uuids(serializer.validated_data.get('known_uuids', []))
        data = {
            'result': 1,
            'unknown_uuids': unknown_uuids,
        }
        hooks.call_hooks('api_modify_response', self, 'synchronization', data)
        return Response(data)

    @detail_route(methods=['post'], url_path='password-reset', permission_classes=(DjangoPermission('custom_user.reset_password_user'),))
    def password_reset(self, request, uuid):
        user = self.get_object()
        # An user without email cannot receive the token
        if not user.email:
            return Response({'result': 0, 'reason': 'User has no mail'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        utils.send_password_reset_mail(user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @detail_route(methods=['post'],
                  permission_classes=(DjangoPermission('custom_user.change_user'),))
    def email(self, request, uuid):
        user = self.get_object()
        serializer = ChangeEmailSerializer(data=request.data)
        if not serializer.is_valid():
            response = {
                'result': 0,
                'errors': serializer.errors
            }
            return Response(response, status.HTTP_400_BAD_REQUEST)
        utils.send_email_change_email(user, serializer.validated_data['email'], request=request)
        return Response({'result': 1})


class RolesAPI(ExceptionHandlerMixin, ModelViewSet):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = RoleSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        return self.request.user.filter_by_perm('a2_rbac.view_role', get_role_model().objects.all())

    def perform_destroy(self, instance):
        if not self.request.user.has_perm(perm='a2_rbac.delete_role', obj=instance):
            raise PermissionDenied(u'User %s can\'t create role %s' % (self.request.user, instance))
        super(RolesAPI, self).perform_destroy(instance)


class RoleMembershipsAPI(ExceptionHandlerMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def initial(self, request, *args, **kwargs):
        super(RoleMembershipsAPI, self).initial(request, *args, **kwargs)
        Role = get_role_model()
        User = get_user_model()
        self.role = get_object_or_404(Role, uuid=kwargs['role_uuid'])
        self.member = get_object_or_404(User, uuid=kwargs['member_uuid'])

        perm = 'a2_rbac.change_role'
        authorized = request.user.has_perm(perm, obj=self.role)
        if not authorized:
            raise PermissionDenied(u'User not allowed to change role')

    def post(self, request, *args, **kwargs):
        self.role.members.add(self.member)
        return Response({'result': 1, 'detail': _('User successfully added to role')},
                        status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        self.role.members.remove(self.member)
        return Response({'result': 1, 'detail': _('User successfully removed from role')},
                        status=status.HTTP_200_OK)

role_memberships = RoleMembershipsAPI.as_view()


class BaseOrganizationalUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_ou_model()
        fields = '__all__'


class OrganizationalUnitAPI(ExceptionHandlerMixin, ModelViewSet):
    permission_classes = (DjangoPermission('a2_rbac.search_organizationalunit'),)
    serializer_class = BaseOrganizationalUnitSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        return get_ou_model().objects.all()

router = SimpleRouter()
router.register(r'users', UsersAPI, base_name='a2-api-users')
router.register(r'ous', OrganizationalUnitAPI, base_name='a2-api-ous')
router.register(r'roles', RolesAPI, base_name='a2-api-roles')


class CheckPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True)


class CheckPasswordAPI(BaseRpcView):
    permission_classes = (DjangoPermission('custom_user.search_user'),)
    serializer_class = CheckPasswordSerializer

    def rpc(self, request, serializer):
        username = serializer.validated_data['username']
        password = serializer.validated_data['password']
        result = {}
        for authenticator in self.get_authenticators():
            if hasattr(authenticator, 'authenticate_credentials'):
                try:
                    user, oidc_client = authenticator.authenticate_credentials(username, password)
                    result['result'] = 1
                    if hasattr(user, 'oidc_client'):
                        result['oidc_client'] = True
                    break
                except AuthenticationFailed as exc:
                    result['result'] = 0
                    result['errors'] = [exc.detail]
        return result, status.HTTP_200_OK


check_password = CheckPasswordAPI.as_view()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # To not perform the csrf check previously happening


class ValidatePasswordSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, allow_blank=True)



class ValidatePasswordAPI(BaseRpcView):
    permission_classes = ()
    authentication_classes = (CsrfExemptSessionAuthentication,)
    serializer_class = ValidatePasswordSerializer

    def rpc(self, request, serializer):
        password_checker = get_password_checker()
        checks = []
        result = {'result': 1, 'checks': checks}
        ok = True
        for check in password_checker(serializer.validated_data['password']):
            ok = ok and check.result
            checks.append({
                'result': check.result,
                'label': check.label,
            })
        result['ok'] = ok
        return result, status.HTTP_200_OK


validate_password = ValidatePasswordAPI.as_view()
