"""Restauração real em cluster descartável e recusa de backups adulterados."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.operations import recovery
from tests.postgres_support import seed_audit_fixture


def test_tampered_backup_never_creates_restore_targets(tmp_path, monkeypatch):
    (tmp_path/'postgres.dump').write_bytes(b'tampered')
    (tmp_path/'manifest.json').write_text(json.dumps({'format': 1,
        'postgres': {'filename': 'postgres.dump', 'sha256': '0'*64}, 'minio': []}))
    cluster = Mock(side_effect=AssertionError('must not restore'))
    monkeypatch.setattr(recovery, 'temporary_postgres', cluster)
    with pytest.raises(ValueError, match='checksum'):
        recovery.verify(tmp_path)
    cluster.assert_not_called()


def test_backup_file_cannot_escape_backup_directory(tmp_path):
    with pytest.raises(ValueError):
        recovery.checked_file(tmp_path, '../outside', '0'*64)


def test_dump_restores_identical_rows_in_disposable_postgres(postgres, tmp_path, monkeypatch):
    database, _ = postgres
    seed_audit_fixture(database)
    backup = recovery.postgres_backup(tmp_path,
        database.connection_url.translate_connect_args(username='user', database='dbname'))
    (tmp_path/'manifest.json').write_text(json.dumps({'format': 1, 'postgres': backup, 'minio': []}))
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = []
    monkeypatch.setattr(recovery, 'get_minio_client', lambda: client)
    result = recovery.verify(tmp_path)
    assert result['postgres_tables'] == 8
    assert result['status'] == 'SUCCESS'
    bucket = client.create_bucket.call_args.kwargs['Bucket']
    assert bucket.startswith('eci-recovery-') and bucket not in recovery.BUCKETS
    client.delete_bucket.assert_called_once_with(Bucket=bucket)
    assert database('SELECT COUNT(*) FROM warehouse.fato_reclamacao') == '2'
