import logging

from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Clean expired models of authentic2.'

    def handle(self, **options):
        log = logging.getLogger(__name__)
        for app in apps.get_app_configs():
            for model in app.get_models():
                # only models from authentic2
                if model.__module__.startswith('authentic2'):
                    try:
                        self.cleanup_model(model)
                    except:
                        log.exception('cleanup of model %s failed', model)

    def cleanup_model(self, model):
        manager = getattr(model, 'objects', None)
        if hasattr(manager, 'cleanup'):
            manager.cleanup()
