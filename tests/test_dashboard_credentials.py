"""Isolamento das credenciais analíticas sem conexão externa."""
from unittest.mock import Mock

import pytest

from src.database import connection


def test_dashboard_uses_separate_credentials(monkeypatch):
    monkeypatch.setenv('DASHBOARD_DB_USER', 'reader')
    monkeypatch.setenv('DASHBOARD_DB_PASSWORD', 'reader-password')
    monkeypatch.setenv('DB_USER', 'writer')
    monkeypatch.setenv('DB_PASSWORD', 'writer-password')
    create = Mock()
    monkeypatch.setattr(connection, 'create_engine', create)
    connection.get_dashboard_engine()
    url = create.call_args.args[0]
    assert url.username == 'reader'
    assert url.password == 'reader-password'
    connection.get_engine()
    assert create.call_args.args[0].username == 'writer'


def test_dashboard_partial_credentials_fail_closed(monkeypatch):
    monkeypatch.setenv('DASHBOARD_DB_USER', 'reader')
    monkeypatch.delenv('DASHBOARD_DB_PASSWORD', raising=False)
    create = Mock()
    monkeypatch.setattr(connection, 'create_engine', create)
    with pytest.raises(ValueError):
        connection.get_dashboard_engine()
    create.assert_not_called()


def test_dashboard_legacy_credentials(monkeypatch):
    monkeypatch.delenv('DASHBOARD_DB_USER', raising=False)
    monkeypatch.delenv('DASHBOARD_DB_PASSWORD', raising=False)
    legacy = Mock()
    monkeypatch.setattr(connection, 'get_engine', legacy)
    assert connection.get_dashboard_engine() is legacy.return_value
