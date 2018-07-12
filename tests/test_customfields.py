import pytest

from authentic2.saml.models import KeyValue, NAME_ID_FORMATS_CHOICES, SPOptionsIdPPolicy

# Adaptation of http://djangosnippets.org/snippets/513/


class CustomDataType(str):
    pass


@pytest.fixture
def testing_data():
    return (
            {1: 1, 2: 4, 3: 6, 4: 8, 5: 10},
            'Hello World',
            (1, 2, 3, 4, 5),
            [1, 2, 3, 4, 5],
            CustomDataType('Hello World'),
        )


def test_pickled_data_integriry(db, testing_data):
    """Tests that data remains the same when saved to and fetched from the database."""
    for value in testing_data:
        model_test = KeyValue(value=value)
        model_test.save()
        model_test = KeyValue.objects.get(key__exact=model_test.key)
        assert value == model_test.value
        model_test.delete()


def test_pickled_lookups(db, testing_data):
    """Tests that lookups can be performed on data once stored in the database."""
    for value in testing_data:
        model_test = KeyValue(value=value)
        model_test.save()
        assert value == KeyValue.objects.get(value__exact=value).value
        model_test.delete()


def test_multiselectfield_data_integrity(db):
    spp = SPOptionsIdPPolicy.objects.create(name='spp')
    value = [x[0] for x in NAME_ID_FORMATS_CHOICES]
    spp.accepted_name_id_format = value
    spp.save()
    spp = SPOptionsIdPPolicy.objects.get(name='spp')
    assert spp.accepted_name_id_format == value


def test_multiselectfield_lookup(db):
    value = [x[0] for x in NAME_ID_FORMATS_CHOICES]
    SPOptionsIdPPolicy.objects.create(name='spp', accepted_name_id_format=value)
    assert SPOptionsIdPPolicy.objects.get(accepted_name_id_format=value).accepted_name_id_format \
        == value
