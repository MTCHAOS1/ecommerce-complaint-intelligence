"""Republicações, preservação da Bronze e resultados da coleta, sem rede real."""
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import requests

from src.ingestion import backfill
from src.ingestion import download_complaints


def archive(path, content):
    with ZipFile(path, 'w') as zipped:
        zipped.writestr('finalizadas_2026-09.csv', content)
    return path.read_bytes()


@pytest.mark.parametrize('force', [False, True])
def test_redownload_replaces_valid_local_zip_only_when_forced(tmp_path, monkeypatch, force):
    monkeypatch.setattr(backfill, 'RAW_DIR', tmp_path)
    target = backfill.local_zip_path('2026-09')
    original = archive(target, 'old')
    updated = archive(tmp_path / 'updated.zip', 'new')
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [updated]
    get = Mock(return_value=response)
    monkeypatch.setattr(backfill.requests, 'get', get)
    backfill.download_zip({'codigo': 1, 'tamanhoArquivo': len(updated)}, '2026-09', force=force)
    assert target.read_bytes() == (updated if force else original)
    assert get.call_count == int(force)
    assert not target.with_suffix('.zip.part').exists()


@pytest.mark.parametrize('failure', ['network', 'invalid_zip', 'wrong_size'])
def test_failed_redownload_preserves_existing_bronze(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(backfill, 'RAW_DIR', tmp_path)
    target = backfill.local_zip_path('2026-09')
    original = archive(target, 'old')
    updated = archive(tmp_path / 'updated.zip', 'new')
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [b'not a zip' if failure == 'invalid_zip' else updated]
    if failure == 'network':
        response.iter_content.side_effect = requests.ConnectionError('interrupted')
    monkeypatch.setattr(backfill.requests, 'get', Mock(return_value=response))
    with pytest.raises((requests.ConnectionError, RuntimeError)):
        backfill.download_zip({'codigo': 1, 'tamanhoArquivo': len(updated) + 1 if failure == 'wrong_size' else len(updated)}, '2026-09', force=True)
    assert target.read_bytes() == original
    assert not target.with_suffix('.zip.part').exists()


def test_forced_collection_bypasses_existing_objects_and_preserves_status(monkeypatch):
    # Invoke the body; lock behavior is covered by the process integration tests.
    engine, client = Mock(), Mock()
    monkeypatch.setattr(backfill, 'get_engine', lambda: engine)
    monkeypatch.setattr(backfill, 'get_minio_client', lambda: client)
    monkeypatch.setattr(backfill, 'register_periods', Mock())
    existing = Mock(side_effect=AssertionError('must consult source'))
    monkeypatch.setattr(backfill, 'check_existing_files', existing)
    catalog = Mock(return_value=({}, 'API', True))
    monkeypatch.setattr(backfill, 'get_dataset_catalog', catalog)
    process = Mock(side_effect=['FAILED', 'PENDING'])
    monkeypatch.setattr(backfill, 'process_pending_period', process)
    result = backfill.run_backfill.__wrapped__(2026, 8, 9, 0, force_download=True, return_results=True)
    assert result == {'2026-08': 'FAILED', '2026-09': 'PENDING'}
    catalog.assert_called_once_with(allow_cache=False)
    assert all(call.kwargs == {'force_download': True} for call in process.call_args_list)
    engine.dispose.assert_called_once()


def test_failed_collection_disposes_engine(monkeypatch):
    engine = Mock()
    monkeypatch.setattr(backfill, 'get_engine', lambda: engine)
    monkeypatch.setattr(backfill, 'get_minio_client', Mock(side_effect=RuntimeError('unavailable')))
    with pytest.raises(RuntimeError):
        backfill.run_backfill.__wrapped__(2026, 9, 9, 0)
    engine.dispose.assert_called_once()


def test_forced_catalog_does_not_use_stale_metadata(monkeypatch):
    monkeypatch.setattr(backfill, 'load_cache', lambda: {'old.zip': {'codigo': 1}})
    monkeypatch.setattr(backfill, 'get_publications', Mock(side_effect=requests.ConnectionError('offline')))
    assert backfill.get_dataset_catalog(allow_cache=False) == ({}, 'UNAVAILABLE', False)


def test_forced_catalog_does_not_merge_removed_publications(monkeypatch):
    monkeypatch.setattr(backfill, 'load_cache', lambda: {'old.zip': {'codigo': 1}})
    monkeypatch.setattr(backfill, 'get_publications', lambda: [])
    monkeypatch.setattr(backfill, 'get_complaint_datasets', lambda _: [
        {'nomeArquivo': 'finalizadas_2026-09.zip', 'codigo': 2},
    ])
    monkeypatch.setattr(backfill, 'save_cache', Mock())
    catalog, origin, available = backfill.get_dataset_catalog(allow_cache=False)
    assert 'old.zip' not in catalog
    assert origin == 'API' and available


def test_local_ingestion_paths_do_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = download_complaints.PROJECT_ROOT / 'data' / 'raw'
    assert download_complaints.RAW_DIR == expected
    assert expected.is_absolute()


def test_failed_download_is_recorded_without_upload(monkeypatch):
    for name in ('mark_source_status', 'mark_attempt', 'mark_failure', 'mark_success', 'upload_bronze'):
        monkeypatch.setattr(backfill, name, Mock())
    download = Mock(side_effect=requests.ConnectionError('offline'))
    monkeypatch.setattr(backfill, 'download_zip', download)
    dataset = {'codigo': 7}
    result = backfill.process_pending_period(
        Mock(), Mock(), '2026-09', {'finalizadas_2026-09.zip': dataset},
        'API', True, force_download=True,
    )
    assert result == 'FAILED'
    download.assert_called_once_with(dataset, '2026-09', force=True)
    backfill.mark_failure.assert_called_once()
    backfill.upload_bronze.assert_not_called()
    backfill.mark_success.assert_not_called()


@pytest.mark.parametrize('status,expected', [('EXISTS', True), ('PENDING', False)])
def test_backfill_preserves_boolean_return_for_existing_callers(monkeypatch, status, expected):
    engine = Mock()
    monkeypatch.setattr(backfill, 'get_engine', lambda: engine)
    monkeypatch.setattr(backfill, 'get_minio_client', Mock())
    monkeypatch.setattr(backfill, 'register_periods', Mock())
    monkeypatch.setattr(backfill, 'check_existing_files', lambda *args: ([], {'2026-09': status}))
    assert backfill.run_backfill.__wrapped__(2026, 9, 9, 0) is expected
    engine.dispose.assert_called_once()
