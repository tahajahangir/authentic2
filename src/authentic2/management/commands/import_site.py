import contextlib
import json
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import translation

from authentic2.data_transfer import import_site, ImportContext


class DryRunException(Exception):
    pass


def create_context_args(options):
    kwargs = {}
    if options['option']:
        for context_op in options['option']:
            context_op = context_op.replace('-', '_')
            if context_op.startswith('no_'):
                kwargs[context_op[3:]] = False
            else:
                kwargs[context_op] = True
    return kwargs


#  Borrowed from https://bugs.python.org/issue10049#msg118599
@contextlib.contextmanager
def provision_contextm(dry_run, settings):
    if dry_run and 'hobo.agent.authentic2' in settings.INSTALLED_APPS:
        import hobo.agent.authentic2
        with hobo.agent.authentic2.provisionning.Provisionning():
            yield
    else:
        yield


class Command(BaseCommand):
    help = 'Import site'

    def add_arguments(self, parser):
        parser.add_argument(
            'filename', metavar='FILENAME', type=str, help='name of file to import')
        parser.add_argument(
            '--dry-run', action='store_true', dest='dry_run', help='Really perform the import')
        parser.add_argument(
            '-o', '--option', action='append', help='Import context options',
            choices=[
                'role-delete-orphans', 'ou-delete-orphans', 'no-role-permissions-update',
                'no-role-attributes-update', 'no-role-parentings-update'])

    def handle(self, filename, **options):
        translation.activate(settings.LANGUAGE_CODE)
        dry_run = options['dry_run']
        msg = "Dry run\n" if dry_run else "Real run\n"
        c_kwargs = create_context_args(options)
        try:
            with open(filename, 'r') as f:
                with provision_contextm(dry_run, settings):
                    with transaction.atomic():
                        sys.stdout.write(msg)
                        result = import_site(json.load(f), ImportContext(**c_kwargs))
                        if dry_run:
                            raise DryRunException()
        except DryRunException:
            pass
        sys.stdout.write(result.to_str())
        sys.stdout.write("Success\n")
        translation.deactivate()
