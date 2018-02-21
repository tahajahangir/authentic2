from authentic2.decorators import GlobalCache


@GlobalCache(timeout=60)
def get_entity_ids():
    from .models import LibertyProvider

    return LibertyProvider.objects.values_list('entity_id', flat=True)


@GlobalCache(timeout=60)
def saml_good_next_url(next_url):
    from authentic2.utils import same_origin

    entity_ids = get_entity_ids()
    for entity_id in entity_ids:
        if same_origin(entity_id, next_url):
            return True
    return None


