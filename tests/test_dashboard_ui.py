"""Interações reais Streamlit com dados sintéticos; nenhuma conexão ao banco."""
import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="Requer dependências opcionais do dashboard.")
pytest.importorskip("plotly", reason="Requer dependências opcionais do dashboard.")
from streamlit.testing.v1 import AppTest

from dashboard.views import overview


APP = Path(__file__).resolve().parents[1] / 'dashboard/app.py'


@pytest.fixture
def dashboard(monkeypatch):
    periods = pd.DataFrame({'ano': [2025, 2026, 2026], 'mes': [2, 1, 3], 'total': [4, 2, 5]})
    monkeypatch.setattr(overview, 'periodos_disponiveis', lambda: periods)
    def data(year, months):
        monthly = periods[(periods.ano == year) & periods.mes.isin(months)]
        total = int(monthly.total.sum())
        has_time = year == 2026 and 1 in months
        return {
            'indicadores': pd.DataFrame([{'reclamacoes': total, 'empresas': 1, 'ufs': 1,
                                         'tempo_medio': 10 if has_time else None,
                                         'base_tempo': 2 if has_time else 0,
                                         'nota_media': None, 'base_nota': 0}]),
            'mensal': monthly[['mes', 'total']].rename(columns={'total': 'reclamacoes'}),
            'empresas': pd.DataFrame({'empresa': ['Empresa'], 'reclamacoes': [total]}),
            'estados': pd.DataFrame({'uf': ['SP'], 'reclamacoes': [total]}),
            'areas': pd.DataFrame({'area': ['Área'], 'reclamacoes': [total]}),
        }
    provider = Mock(side_effect=data)
    monkeypatch.setattr(overview, 'carregar_visao_geral', provider)
    return AppTest.from_file(APP, default_timeout=10), provider


def test_month_filter_changes_kpis_and_monthly_chart(dashboard):
    app, provider = dashboard
    app.run()
    assert not app.exception
    assert app.metric[0].value == '7'
    assert app.multiselect[0].options == ['Janeiro', 'Março']
    app.multiselect[0].set_value([3]).run()
    assert not app.exception
    assert app.metric[0].value == '5'
    assert provider.call_args.args == (2026, [3])
    plot = json.loads(app.get('plotly_chart')[0].proto.spec)
    assert plot['data'][0]['x'] == ['Março']
    assert app.metric[3].value == 'N/D'
    assert app.metric[4].value == 'N/D'
    assert any('Base: 0 reclamações com nota' in item.value for item in app.caption)


def test_empty_month_selection_stops_before_query(dashboard):
    app, provider = dashboard
    app.run()
    provider.reset_mock()
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    provider.assert_not_called()
    assert not app.metric
    assert not app.get('plotly_chart')
    assert any('Selecione pelo menos um mês' in item.value for item in app.info)


def test_year_switch_only_offers_months_loaded_in_that_year(dashboard):
    app, provider = dashboard
    app.run()
    app.multiselect[0].set_value([3]).run()
    app.selectbox[0].select(2025).run()
    assert not app.exception
    assert app.multiselect[0].options == ['Fevereiro']
    assert provider.call_args.args == (2025, [2])
    assert app.metric[0].value == '4'
    assert any('Ausência de carga não representa zero' in item.value for item in app.info)


def test_empty_warehouse_does_not_render_metrics(dashboard, monkeypatch):
    app, provider = dashboard
    monkeypatch.setattr(overview, 'periodos_disponiveis', lambda: pd.DataFrame(columns=['ano', 'mes', 'total']))
    app.run()
    assert not app.exception
    provider.assert_not_called()
    assert not app.metric
    assert app.warning[0].value == 'Nenhum período foi carregado na Gold.'


def test_query_failure_is_handled_without_exposing_details(dashboard):
    app, provider = dashboard
    provider.side_effect = RuntimeError('private-connection-details')
    app.run()
    assert not app.exception
    assert app.error
    assert 'private-connection-details' not in app.error[0].value
    assert not app.metric


def test_other_pages_remain_accessible_without_overview_filters(dashboard):
    app, provider = dashboard
    app.run()
    provider.reset_mock()
    app.radio[0].set_value('Empresas').run()
    assert not app.exception
    assert not app.multiselect
    provider.assert_not_called()
    assert any(header.value == 'Empresas' for header in app.header)


def test_zero_time_is_displayed_as_zero_not_missing(dashboard):
    app, provider = dashboard
    original = provider.side_effect
    def zero_time(year, months):
        data = original(year, months)
        data['indicadores'].loc[0, 'tempo_medio'] = 0
        return data
    provider.side_effect = zero_time
    app.run()
    assert not app.exception
    assert app.metric[3].value == '0,00'


def test_refresh_button_clears_analytics_cache(dashboard, monkeypatch):
    app, provider = dashboard
    clear = Mock()
    monkeypatch.setattr(overview.consultar_lote, 'clear', clear)
    app.run()
    clear.assert_not_called()
    app.button[0].click().run()
    assert not app.exception
    clear.assert_called_once()
