import __builtin__
import json

from django.core import management
import pytest

from django_rbac.utils import get_role_model


def dummy_export_site(*args):
    return {'roles': [{'name': 'role1'}]}


def test_export_role_cmd_stdout(db, capsys, monkeypatch):
    import authentic2.management.commands.export_site
    monkeypatch.setattr(
        authentic2.management.commands.export_site, 'export_site', dummy_export_site)
    management.call_command('export_site')
    out, err = capsys.readouterr()
    assert json.loads(out) == dummy_export_site()


def test_export_role_cmd_to_file(db, monkeypatch, tmpdir):
    import authentic2.management.commands.export_site
    monkeypatch.setattr(
        authentic2.management.commands.export_site, 'export_site', dummy_export_site)
    outfile = tmpdir.join('export.json')
    management.call_command('export_site', '--output', outfile.strpath)
    with outfile.open('r') as f:
        assert json.loads(f.read()) == dummy_export_site()


def test_import_site_cmd(db, tmpdir, monkeypatch):
    export_file = tmpdir.join('roles-export.json')
    with export_file.open('w'):
        export_file.write(json.dumps({'roles': []}))
    management.call_command('import_site', export_file.strpath)


def test_import_site_cmd_infos_on_stdout(db, tmpdir, monkeypatch, capsys):
    export_file = tmpdir.join('roles-export.json')
    with export_file.open('w'):
        export_file.write(json.dumps(
            {'roles': [{
                'uuid': 'dqfewrvesvews2532', 'slug': 'role-slug', 'name': 'role-name',
                'ou': None, 'service': None}]}))

    management.call_command('import_site', export_file.strpath)

    out, err = capsys.readouterr()
    assert "Real run" in out
    assert "1 roles created" in out
    assert "0 roles updated" in out


def test_import_site_transaction_rollback_on_error(db, tmpdir, monkeypatch, capsys):
    export_file = tmpdir.join('roles-export.json')
    with export_file.open('w'):
        export_file.write(json.dumps({'roles': []}))

    Role = get_role_model()

    def exception_import_site(*args):
        Role.objects.create(slug='role-slug')
        raise Exception()

    import authentic2.management.commands.import_site
    monkeypatch.setattr(
        authentic2.management.commands.import_site, 'import_site', exception_import_site)

    with pytest.raises(Exception):
        management.call_command('import_site', export_file.strpath)

    with pytest.raises(Role.DoesNotExist):
        Role.objects.get(slug='role-slug')


def test_import_site_transaction_rollback_on_dry_run(db, tmpdir, monkeypatch, capsys):
    export_file = tmpdir.join('roles-export.json')
    with export_file.open('w'):
        export_file.write(json.dumps(
            {'roles': [{
                'uuid': 'dqfewrvesvews2532', 'slug': 'role-slug', 'name': 'role-name',
                'ou': None, 'service': None}]}))

    Role = get_role_model()

    management.call_command('import_site', '--dry-run', export_file.strpath)

    with pytest.raises(Role.DoesNotExist):
        Role.objects.get(slug='role-slug')


def test_import_site_cmd_unhandled_context_option(db, tmpdir, monkeypatch, capsys):
    from authentic2.data_transfer import DataImportError

    export_file = tmpdir.join('roles-export.json')
    with export_file.open('w'):
        export_file.write(json.dumps(
            {'roles': [{
                'uuid': 'dqfewrvesvews2532', 'slug': 'role-slug', 'name': 'role-name',
                'ou': None, 'service': None}]}))

    get_role_model().objects.create(uuid='dqfewrvesvews2532', slug='role-slug', name='role-name')

    with pytest.raises(DataImportError):
        management.call_command(
            'import_site', '-o', 'role-delete-orphans', export_file.strpath)


def test_import_site_cmd_unknown_context_option(db, tmpdir, monkeypatch, capsys):
    from django.core.management.base import CommandError
    export_file = tmpdir.join('roles-export.json')
    with pytest.raises(CommandError):
        management.call_command('import_site', '-o', 'unknown-option', export_file.strpath)


def test_import_site_confirm_prompt_yes(db, tmpdir, monkeypatch):
    export_file = tmpdir.join('roles-export.json')
    with export_file.open('w'):
        export_file.write(json.dumps(
            {'roles': [{
                'uuid': 'dqfewrvesvews2532', 'slug': 'role-slug', 'name': 'role-name',
                'ou': None, 'service': None}]}))

    def yes_raw_input(*args, **kwargs):
        return 'yes'

    monkeypatch.setattr(__builtin__, 'raw_input', yes_raw_input)

    management.call_command('import_site', export_file.strpath, stdin='yes')
    assert get_role_model().objects.get(uuid='dqfewrvesvews2532')
