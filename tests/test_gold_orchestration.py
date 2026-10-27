"""Carga auditada usa a conexão do lock e encerra falhas após RUNNING."""
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

import pytest
from src.database import load_gold as gold


@pytest.fixture
def orchestration(monkeypatch):
    connection = MagicMock()
    @contextmanager
    def operation():
        yield connection
    monkeypatch.setattr(gold, 'pipeline_operation', operation)
    # O decorador também usa o contexto do módulo gold_lock.
    from src.database import gold_lock
    monkeypatch.setattr(gold_lock, 'pipeline_operation', operation)
    mocks = {'connection': connection}
    for name, value in [('start_gold_execution', (42, 1)), ('count_gold_records', 1),
                        ('finish_gold_execution', None), ('fail_gold_execution', None)]:
        mocks[name] = Mock(return_value=value)
        monkeypatch.setattr(gold, name, mocks[name])
    return mocks


def test_gold_passes_expected_period_in_same_connection(orchestration):
    gold.load_gold('2026-07')
    call = orchestration['connection'].execute.call_args
    assert call.args[1] == {'period': '2026-07'}
    orchestration['connection'].exec_driver_sql.assert_called_once()
    orchestration['finish_gold_execution'].assert_called_once_with(42, 1)
    orchestration['fail_gold_execution'].assert_not_called()


def test_sql_failure_finishes_failed_audit(orchestration):
    orchestration['connection'].exec_driver_sql.side_effect = RuntimeError('falha SQL')
    with pytest.raises(RuntimeError, match='falha SQL'):
        gold.load_gold('2026-07')
    orchestration['fail_gold_execution'].assert_called_once()
    orchestration['finish_gold_execution'].assert_not_called()


def test_preparation_failure_after_running_finishes_failed_audit(monkeypatch, orchestration):
    sql_file = Mock()
    sql_file.is_file.return_value = True
    sql_file.read_text.side_effect = OSError('arquivo indisponível')
    monkeypatch.setattr(gold, 'GOLD_SQL_FILE', sql_file)
    with pytest.raises(OSError, match='arquivo indisponível'):
        gold.load_gold('2026-07')
    orchestration['fail_gold_execution'].assert_called_once()
    assert orchestration['fail_gold_execution'].call_args.args[0] == 42
    orchestration['connection'].exec_driver_sql.assert_not_called()


def test_post_commit_count_failure_is_audited(orchestration):
    orchestration['count_gold_records'].return_value = 2
    with pytest.raises(RuntimeError, match='após COMMIT'):
        gold.load_gold('2026-07')
    orchestration['fail_gold_execution'].assert_called_once()
    orchestration['finish_gold_execution'].assert_not_called()
