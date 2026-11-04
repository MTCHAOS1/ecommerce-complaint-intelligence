"""Retomada mensal e falhas parciais da atualização recorrente."""
from contextlib import contextmanager
from datetime import date
from unittest.mock import Mock

import pytest

from src.ingestion import refresh as module
from tests.postgres_support import seed_audit_fixture


def test_calendar_crosses_year_and_excludes_current_month():
    assert module.select_periods(today=date(2027, 2, 4)) == [
        '2026-11', '2026-12', '2027-01']
    assert module.select_periods('2026-12', '2027-01', today=date(2027, 2, 4)) == [
        '2026-12', '2027-01']


@pytest.mark.parametrize('arguments', [
    {'start': '2026-01'}, {'end': '2026-02'}, {'lookback': 0},
    {'start': '2026-02', 'end': '2026-01'},
    {'start': '2026-01', 'end': '2026-11'},
    {'start': '2026-13', 'end': '2026-13'},
    {'start': '1999-01', 'end': '1999-02'},
    {'start': '2000-01', 'end': '2020-01'},
])
def test_invalid_range_is_rejected(arguments):
    with pytest.raises(ValueError):
        module.select_periods(today=date(2026, 11, 4), **arguments)


@pytest.fixture
def operations(monkeypatch):
    held = []
    @contextmanager
    def lock():
        held.append(True)
        try:
            yield Mock()
        finally:
            held.pop()
    monkeypatch.setattr(module, 'pipeline_operation', lock)
    calls = []
    for name in ('run_backfill', 'transform', 'load_staging', 'load_gold'):
        def operation(*args, _name=name, **kwargs):
            assert held, 'Toda etapa precisa manter o lock.'
            calls.append((_name, args, kwargs))
            return True
        monkeypatch.setattr(module, name, Mock(side_effect=operation))
    monkeypatch.setattr(module, 'is_complete', Mock(return_value=False))
    return calls


def test_skips_audited_month_and_processes_missing_month(operations, monkeypatch):
    module.is_complete.side_effect = [True, False]
    assert module.refresh(['2026-08', '2026-09'], delay=0) == {
        '2026-08': 'SKIPPED', '2026-09': 'SUCCESS'}
    assert operations == [
        ('run_backfill', (2026, 9, 9, 0), {}),
        ('transform', ('2026-09', 'minio'), {'upload': True}),
        ('load_staging', ('2026-09', 'minio'), {}),
        ('load_gold', ('2026-09',), {}),
    ]


def test_pending_bronze_never_loads_staging_or_gold(operations):
    module.run_backfill.return_value = False
    module.run_backfill.side_effect = None
    assert module.refresh(['2026-09'], delay=0) == {'2026-09': 'PENDING'}
    module.transform.assert_not_called()
    module.load_staging.assert_not_called()
    module.load_gold.assert_not_called()


def test_failure_does_not_stop_next_month_or_load_failed_month_gold(operations):
    module.load_staging.side_effect = [ValueError('falha simulada'), None]
    assert module.refresh(['2026-08', '2026-09'], delay=0) == {
        '2026-08': 'FAILED', '2026-09': 'SUCCESS'}
    module.load_gold.assert_called_once_with('2026-09')


def test_explicit_reprocess_bypasses_skip(operations):
    assert module.refresh(['2026-09'], reprocess=True, delay=0) == {'2026-09': 'SUCCESS'}
    module.is_complete.assert_not_called()


def test_lock_rejection_prevents_work(monkeypatch):
    @contextmanager
    def denied():
        raise RuntimeError('lock ocupado')
        yield
    monkeypatch.setattr(module, 'pipeline_operation', denied)
    forbidden = Mock(side_effect=AssertionError('não deve coletar'))
    monkeypatch.setattr(module, 'run_backfill', forbidden)
    with pytest.raises(RuntimeError, match='lock ocupado'):
        module.refresh(['2026-09'])
    forbidden.assert_not_called()


def test_plan_never_connects(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['refresh', '--start', '2026-08', '--end', '2026-09', '--plan'])
    monkeypatch.setattr(module, 'refresh', Mock(side_effect=AssertionError('não deve executar')))
    module.main()
    assert '2026-08, 2026-09' in capsys.readouterr().out


def test_cli_incomplete_returns_failure(monkeypatch):
    monkeypatch.setattr('sys.argv', ['refresh', '--start', '2026-08', '--end', '2026-09'])
    monkeypatch.setattr(module, 'refresh', Mock(return_value={
        '2026-08': 'SUCCESS', '2026-09': 'PENDING'}))
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 1


def test_real_sql_requires_latest_success_and_matching_counts(postgres):
    database, _ = postgres
    seed_audit_fixture(database)
    from sqlalchemy import create_engine
    engine = create_engine(database.connection_url)
    try:
        with engine.connect() as connection:
            # SQL fixture carrega fatos sem criar auditoria Python.
            assert not module.is_complete(connection, '2026-07')
            database("""
                INSERT INTO metadata.gold_load_control
                    (periodo, status, registros_staging, registros_gold, finalizado_em)
                VALUES ('2026-07-01', 'SUCCESS', 2, 2, NOW());
            """)
            assert module.is_complete(connection, '2026-07')
            assert not module.is_complete(connection, '2026-08')
            database("UPDATE metadata.gold_load_control SET registros_gold = 3")
            assert not module.is_complete(connection, '2026-07')
            database("UPDATE metadata.gold_load_control SET registros_gold = 2")
            database("""
                INSERT INTO metadata.gold_load_control
                    (periodo, status, registros_staging)
                VALUES ('2026-07-01', 'RUNNING', 2);
            """)
            assert not module.is_complete(connection, '2026-07')
    finally:
        engine.dispose()
