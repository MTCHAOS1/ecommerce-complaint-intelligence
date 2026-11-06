from unittest.mock import Mock
import pytest
from src.database import connection


def test_reader_secret_file_is_used_without_writer_credentials(tmp_path, monkeypatch):
    path = tmp_path/'password'
    path.write_text('reader-secret\n')
    monkeypatch.delenv('DASHBOARD_DB_PASSWORD', raising=False)
    monkeypatch.setenv('DASHBOARD_DB_USER', 'reader')
    monkeypatch.setenv('DASHBOARD_DB_PASSWORD_FILE', str(path))
    create = Mock()
    monkeypatch.setattr(connection, 'create_engine', create)
    connection.get_dashboard_engine()
    assert create.call_args.args[0].password == 'reader-secret'
    assert create.call_args.args[0].username == 'reader'


def test_ambiguous_secret_sources_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PASSWORD', 'legacy')
    monkeypatch.setenv('DB_PASSWORD_FILE', str(tmp_path/'secret'))
    with pytest.raises(ValueError, match='somente'):
        connection.get_engine()
