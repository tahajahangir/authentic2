import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS

from authentic2.utils import generate_password
from authentic2.models import PasswordReset

class Command(BaseCommand):
    help = "Reset a user's password for django.contrib.auth."

    require_model_validation = False

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', type=str)
        parser.add_argument(
            '--database', action='store', dest='database',
            default=DEFAULT_DB_ALIAS, help='Specifies the database to use. Default is "default".')

    def _get_pass(self, prompt="Password: "):
        p = getpass.getpass(prompt=prompt)
        if not p:
            raise CommandError("aborted")
        return p

    def handle(self, *args, **options):
        username = options['username']
        if not username:
            username = getpass.getuser()

        UserModel = get_user_model()

        try:
            u = UserModel._default_manager.using(options.get('database')).get(**{
                    UserModel.USERNAME_FIELD: username
                })
        except UserModel.DoesNotExist:
            raise CommandError("user '%s' does not exist" % username)

        p1 = generate_password()
        self.stdout.write("Changing password for user '%s' to '%s'\n" % (u, p1))
        u.set_password(p1)
        u.save()
        PasswordReset.objects.get_or_create(user=u)
        return "Password changed successfully for user '%s', on next login he will be forced to change its password." % u

