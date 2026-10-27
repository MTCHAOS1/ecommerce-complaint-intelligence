"""Leitura e resumo dos planos, sem executar medições contra a aplicação."""
from unittest.mock import Mock

import pytest

pytest.importorskip('streamlit', reason='Requer dependências opcionais do dashboard.')
from scripts import benchmark_dashboard as benchmark


def test_explain_rejects_write_before_execution():
    connection = Mock()
    with pytest.raises(ValueError, match='leitura'):
        benchmark.explain_query(connection, 'DELETE FROM warehouse.fato_reclamacao', {})
    connection.execute.assert_not_called()


def test_warmup_is_excluded_and_buffers_are_not_counted_twice(monkeypatch):
    def plan(milliseconds):
        return {'Execution Time': milliseconds, 'Planning Time': 1,
                'Plan': {'Node Type': 'Aggregate', 'Shared Hit Blocks': 10,
                         'Temp Read Blocks': 2,
                         'Plans': [{'Shared Hit Blocks': 9, 'Temp Read Blocks': 2}]}}
    explain = Mock(side_effect=[(plan(99), 100), (plan(12), 13), (plan(8), 9), (plan(10), 11)])
    monkeypatch.setattr(benchmark, 'explain_query', explain)
    result = benchmark.measure_query(Mock(), 'SELECT 1', {}, repetitions=3, warmup=1)
    assert result['median_execution_ms'] == 10
    assert result['median_wall_ms'] == 11
    assert len(result['samples']) == 3
    assert all(sample['shared_hits'] == 10 for sample in result['samples'])
    assert all(sample['temp_reads'] == 2 for sample in result['samples'])
