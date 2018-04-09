import json
import sys

from django.core.management.base import BaseCommand

from authentic2.data_transfer import export_site
from django_rbac.utils import get_role_model


class Command(BaseCommand):
    help = 'Export site'

    def add_arguments(self, parser):
        parser.add_argument('--output', metavar='FILE', default=None,
                            help='name of a file to write output to')

    def handle(self, *args, **options):
        if options['output']:
            output, close = open(options['output'], 'w'), True
        else:
            output, close = sys.stdout, False
        json.dump(export_site(), output, indent=4)
        if close:
            output.close()
