"""Barreiras do provisionamento: nenhum banco informado pelo usuário é removido."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock

import psycopg
import pytest
from sqlalchemy.engine import URL

from tests import postgres_support as support
from tests.database_safety import PreparedDatabaseTestCase


@pytest.fixture
def server(monkeypatch):
    admin = MagicMock()
    admin.info.user = 'ci_user'
    admin.info.host = 'ci-host'
    admin.info.port = 5432
    connect = MagicMock()
    connect.return_value.__enter__.return_value = admin
    monkeypatch.setattr(support.psycopg, 'connect', connect)
    initialize = Mock()
    monkeypatch.setattr(support.TestDatabase, 'initialize', initialize)
    monkeypatch.setattr(support, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    url = URL.create('postgresql+psycopg', username='ci_user', password='test-only',
                     host='ci-host', port=5432, database='ci_control_test')
    return admin, initialize, url


def statements(admin):
    return [str(call.args[0]) for call in admin.execute.call_args_list]


def test_disabled_provisioning_never_connects(monkeypatch):
    monkeypatch.delenv('TEST_DB_NAME', raising=False)
    monkeypatch.delenv('RUN_TEMP_POSTGRES_TESTS', raising=False)
    connect = Mock(side_effect=AssertionError('Não deve conectar'))
    monkeypatch.setattr(support.psycopg, 'connect', connect)
    with pytest.raises(unittest.SkipTest):
        with support.postgres_database():
            pytest.fail('Não deve preparar')
    connect.assert_not_called()


@pytest.mark.parametrize('name', ['postgres', 'production', 'app_test;DROP', '../app_test', 'UPPER_test'])
def test_invalid_control_database_is_rejected_before_connect(monkeypatch, name):
    monkeypatch.delenv('RUN_TEMP_POSTGRES_TESTS', raising=False)
    monkeypatch.setenv('DB_NAME', 'application')
    monkeypatch.setenv('TEST_DB_NAME', name)
    connect = Mock(side_effect=AssertionError('Não deve conectar'))
    monkeypatch.setattr(support.psycopg, 'connect', connect)
    with pytest.raises(RuntimeError, match='banco da aplicação'):
        with support.postgres_database():
            pass
    connect.assert_not_called()


def test_control_database_cannot_equal_application(monkeypatch):
    monkeypatch.delenv('RUN_TEMP_POSTGRES_TESTS', raising=False)
    monkeypatch.setenv('DB_NAME', 'application_test')
    monkeypatch.setenv('TEST_DB_NAME', 'application_test')
    with pytest.raises(RuntimeError, match='banco da aplicação'):
        with support.postgres_database():
            pass


def test_only_created_database_is_initialized_and_dropped(server):
    admin, initialize, url = server
    with support.database_on_server(url, 'psql') as database:
        assert database.connection_url.database == 'eci_' + 'a' * 32 + '_test'
        assert database.environment['DB_NAME'] != 'ci_control_test'
        initialize.assert_called_once()
    commands = statements(admin)
    assert len(commands) == 2
    assert 'CREATE DATABASE' in commands[0] and 'DROP DATABASE' in commands[1]
    assert all('ci_control_test' not in command for command in commands)


def test_failed_create_never_drops_preexisting_database(server):
    admin, initialize, url = server
    admin.execute.side_effect = psycopg.errors.DuplicateDatabase('já existe')
    with pytest.raises(psycopg.errors.DuplicateDatabase):
        with support.database_on_server(url, 'psql'):
            pass
    assert len(statements(admin)) == 1
    assert 'DROP' not in statements(admin)[0]
    initialize.assert_not_called()


def test_missing_createdb_privilege_fails_without_drop(server):
    admin, initialize, url = server
    admin.execute.side_effect = psycopg.errors.InsufficientPrivilege('sem permissão')
    with pytest.raises(RuntimeError, match='CREATEDB'):
        with support.database_on_server(url, 'psql'):
            pass
    assert len(statements(admin)) == 1
    initialize.assert_not_called()


@pytest.mark.parametrize('phase', ['initialization', 'test'])
def test_owned_database_is_dropped_on_failure(server, phase):
    admin, initialize, url = server
    if phase == 'initialization':
        initialize.side_effect = RuntimeError('falha de preparação')
    with pytest.raises(RuntimeError, match='falha'):
        with support.database_on_server(url, 'psql'):
            raise RuntimeError('falha do teste')
    assert 'DROP DATABASE' in statements(admin)[-1]


def test_prepared_class_restores_environment_after_seed_failure(monkeypatch):
    import os
    monkeypatch.setenv('DB_NAME', 'application')
    monkeypatch.setenv('DB_HOST', 'original-host')
    monkeypatch.delenv('TEST_DB_NAME', raising=False)
    released = []
    @contextmanager
    def database():
        try:
            yield support.TestDatabase(URL.create('postgresql+psycopg', username='test',
                                      host='private-socket', database='eci_isolated_test'), 'psql')
        finally:
            released.append(True)
    monkeypatch.setattr(support, 'postgres_database', database)
    monkeypatch.setattr(support, 'seed_audit_fixture', Mock(side_effect=RuntimeError('falha da fixture')))
    class BrokenCase(PreparedDatabaseTestCase):
        def test_never_runs(self):
            raise AssertionError('Preparação falhou')
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(BrokenCase).run(result)
    assert len(result.errors) == 1 and result.testsRun == 0
    assert released == [True]
    assert os.environ['DB_NAME'] == 'application'
    assert os.environ['DB_HOST'] == 'original-host'
    assert 'TEST_DB_NAME' not in os.environ
