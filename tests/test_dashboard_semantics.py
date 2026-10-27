"""Contrato do recorte e leitura consistente do dashboard, sem banco externo."""
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="Requer dependências opcionais do dashboard.")

from dashboard.services import analytics, overview


@pytest.fixture(autouse=True)
def clear_cache():
    analytics.consultar_lote.clear()
    yield
    analytics.consultar_lote.clear()


@pytest.mark.parametrize('year,months', [(0, [1]), (True, [1]), ('2026', [1]),
                                        (2026, []), (2026, [0]), (2026, [13]),
                                        (2026, [True]), (2026, ['1'])])
def test_invalid_selection_never_queries_database(monkeypatch, year, months):
    query = Mock(side_effect=AssertionError('Não deve consultar'))
    monkeypatch.setattr(overview, 'consultar_lote', query)
    with pytest.raises(ValueError):
        overview.carregar_visao_geral(year, months)
    query.assert_not_called()


def test_same_normalized_selection_is_sent_to_all_charts(monkeypatch):
    query = Mock(return_value={})
    monkeypatch.setattr(overview, 'consultar_lote', query)
    overview.carregar_visao_geral(2026, [3, 1, 3])
    assert query.call_args.args[1] == {'ano': 2026, 'meses': [1, 3]}
    assert set(query.call_args.args[0]) == {'indicadores', 'mensal', 'empresas', 'estados', 'areas'}


def test_batch_rejects_write_before_connecting(monkeypatch):
    engine = Mock(side_effect=AssertionError('Não deve conectar'))
    monkeypatch.setattr(analytics, 'get_engine', engine)
    with pytest.raises(ValueError, match='leitura'):
        analytics.consultar_lote({'ok': 'SELECT 1', 'write': 'DELETE FROM warehouse.fato_reclamacao'})
    engine.assert_not_called()


def test_batch_uses_one_connection_and_snapshot(monkeypatch):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = analytics.BANCO_ESPERADO
    monkeypatch.setattr(analytics, 'get_engine', lambda: engine)
    reads = Mock(side_effect=[pd.DataFrame({'a': [1]}), pd.DataFrame({'b': [2]})])
    monkeypatch.setattr(analytics.pd, 'read_sql_query', reads)
    result = analytics.consultar_lote({'one': 'SELECT 1', 'two': 'SELECT 2'}, {'ano': 2026})
    assert set(result) == {'one', 'two'}
    assert all(call.args[1] is connection for call in reads.call_args_list)
    assert 'REPEATABLE READ, READ ONLY' in str(connection.execute.call_args.args[0])
    engine.connect.assert_called_once()
    engine.dispose.assert_called_once()


def test_batch_disposes_engine_on_query_failure(monkeypatch):
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = analytics.BANCO_ESPERADO
    monkeypatch.setattr(analytics, 'get_engine', lambda: engine)
    monkeypatch.setattr(analytics.pd, 'read_sql_query', Mock(side_effect=RuntimeError('falha')))
    with pytest.raises(RuntimeError, match='falha'):
        analytics.consultar_lote({'one': 'SELECT 1'})
    engine.dispose.assert_called_once()


def test_batch_refuses_unexpected_database(monkeypatch):
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = 'unexpected_test'
    monkeypatch.setattr(analytics, 'get_engine', lambda: engine)
    with pytest.raises(RuntimeError, match='Banco inesperado'):
        analytics.consultar_lote({'one': 'SELECT 1'})
    engine.dispose.assert_called_once()
