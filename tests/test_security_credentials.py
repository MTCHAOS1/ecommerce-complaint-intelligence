from unittest.mock import Mock

import pytest

from src.database import connection
from src.storage import minio_client


def test_required_reader_never_falls_back_to_pipeline(monkeypatch):
    monkeypatch.setenv('DASHBOARD_REQUIRE_READER', '1')
    for key in ['DASHBOARD_DB_USER', 'DASHBOARD_DB_PASSWORD', 'DASHBOARD_DB_PASSWORD_FILE']:
        monkeypatch.delenv(key, raising=False)
    writer = Mock()
    monkeypatch.setattr(connection, 'get_engine', writer)
    with pytest.raises(ValueError, match='obrigatórias'):
        connection.get_dashboard_engine()
    writer.assert_not_called()


def test_partial_storage_credentials_never_fall_back_to_root(monkeypatch):
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'pipeline')
    for key in ['MINIO_SECRET_KEY', 'MINIO_SECRET_KEY_FILE', 'MINIO_ACCESS_KEY_FILE']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('MINIO_ROOT_USER', 'admin')
    monkeypatch.setenv('MINIO_ROOT_PASSWORD', 'test-only')
    factory = Mock()
    monkeypatch.setattr(minio_client.boto3, 'client', factory)
    with pytest.raises(RuntimeError, match='juntos'):
        minio_client.get_minio_client()
    factory.assert_not_called()


def test_storage_uses_scoped_account(monkeypatch):
    for key in ['MINIO_SECRET_KEY_FILE', 'MINIO_ACCESS_KEY_FILE']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'pipeline')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'test-only')
    monkeypatch.setenv('MINIO_ROOT_USER', 'admin')
    monkeypatch.setenv('MINIO_ROOT_PASSWORD', 'admin-test-only')
    factory = Mock()
    monkeypatch.setattr(minio_client.boto3, 'client', factory)
    minio_client.get_minio_client()
    assert factory.call_args.kwargs['aws_access_key_id'] == 'pipeline'
