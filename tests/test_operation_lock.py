"""Comandos públicos rejeitam concorrência antes de acessar os dados."""
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

import pytest

from src.database import gold_lock


def test_nested_operations_reuse_connection_and_acquire_once(monkeypatch):
    connection = MagicMock()
    acquisitions = []
    @contextmanager
    def lock():
        acquisitions.append(True)
        token = gold_lock._ACTIVE_OPERATION.set((gold_lock.os.getpid(), gold_lock.threading.get_ident(), connection))
        try:
            yield connection
        finally:
            gold_lock._ACTIVE_OPERATION.reset(token)
    monkeypatch.setattr(gold_lock, 'gold_execution_lock', lock)
    with gold_lock.pipeline_operation() as outer:
        with gold_lock.pipeline_operation() as inner:
            assert inner is outer is connection
    assert acquisitions == [True]
    assert gold_lock._ACTIVE_OPERATION.get() is None


@pytest.mark.parametrize('foreign_owner', ['process', 'thread'])
def test_inherited_context_cannot_bypass_lock(monkeypatch, foreign_owner):
    pid, thread = gold_lock.os.getpid(), gold_lock.threading.get_ident()
    token = gold_lock._ACTIVE_OPERATION.set((pid + (foreign_owner == 'process'), thread + (foreign_owner == 'thread'), MagicMock()))
    try:
        @contextmanager
        def denied():
            raise RuntimeError('lock ocupado')
            yield
        monkeypatch.setattr(gold_lock, 'gold_execution_lock', denied)
        with pytest.raises(RuntimeError, match='lock ocupado'):
            with gold_lock.pipeline_operation():
                pytest.fail('Não deve entrar')
    finally:
        gold_lock._ACTIVE_OPERATION.reset(token)


def test_exception_releases_lock_and_clears_context(monkeypatch):
    engine, connection = MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    connection.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(gold_lock, 'get_engine', lambda: engine)
    with pytest.raises(ValueError, match='falha'):
        with gold_lock.gold_execution_lock():
            raise ValueError('falha')
    queries = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert 'pg_try_advisory_lock' in queries[0]
    assert 'pg_advisory_unlock' in queries[1]
    assert gold_lock._ACTIVE_OPERATION.get() is None
    engine.dispose.assert_called_once()


@pytest.mark.parametrize('operation', [
    'staging', 'silver', 'ingestion', 'backfill', 'sync', 'cache', 'gold',
    'upload', 'normalize', 'download',
])
def test_public_operations_fail_before_any_work(monkeypatch, operation, tmp_path):
    from src.database.load_staging import run as staging
    from src.transformation.transform_complaints import run as silver
    from src.ingestion.download_complaints import run as ingestion
    from src.ingestion.backfill import run_backfill
    from src.storage.sync_data_lake import sync_layer
    from src.storage.download_from_minio import download_from_minio
    from src.database.load_gold import load_gold
    from src.storage.minio_client import upload_file
    from scripts.prepare_bronze_zip import prepare
    from scripts.download_direct import baixar_arquivo
    @contextmanager
    def denied():
        raise RuntimeError('Outra operação Gold está em andamento.')
        yield
    monkeypatch.setattr(gold_lock, 'gold_execution_lock', denied)
    operations = {
        'staging': (staging, ('2026-07',)), 'silver': (silver, ('2026-07',)),
        'ingestion': (ingestion, ('2026-07',)), 'backfill': (run_backfill, (2026, 7, 7, 0)),
        'sync': (sync_layer, ('silver', '2026-07')),
        'cache': (download_from_minio, ('silver', '2026-07')),
        'gold': (load_gold, ('2026-07',)), 'upload': (upload_file, (tmp_path / 'absent', 'bucket')),
        'normalize': (prepare, ('2026-07', tmp_path / 'absent.zip')),
        'download': (baixar_arquivo, ({}, tmp_path)),
    }
    function, arguments = operations[operation]
    with pytest.raises(RuntimeError, match='Outra operação Gold'):
        function(*arguments)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('module_name', [
    'main', 'src.database.load_gold', 'src.database.load_staging', 'src.database.gold_audit',
    'src.transformation.transform_complaints', 'src.ingestion.download_complaints',
    'src.ingestion.backfill', 'src.storage.sync_data_lake',
    'src.storage.download_from_minio', 'scripts.prepare_bronze_zip', 'scripts.download_direct',
])
def test_cli_help_does_not_connect_or_acquire_lock(monkeypatch, module_name):
    import importlib
    import sys
    module = importlib.import_module(module_name)
    forbidden = Mock(side_effect=AssertionError('Ajuda deve funcionar sem PostgreSQL'))
    monkeypatch.setattr(gold_lock, 'get_engine', forbidden)
    monkeypatch.setattr(sys, 'argv', [module_name, '--help'])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    forbidden.assert_not_called()
