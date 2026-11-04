"""Página Empresas: seleção real no Streamlit com dados sintéticos."""
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

pytest.importorskip('streamlit')
pytest.importorskip('plotly')
from streamlit.testing.v1 import AppTest
from dashboard.views import companies


@pytest.fixture
def company_app(monkeypatch):
    monkeypatch.setattr(companies, 'periodos_disponiveis', lambda: pd.DataFrame({'ano': [2026], 'mes': [7]}))
    monkeypatch.setattr(companies, 'listar_empresas', lambda *args: pd.DataFrame({'empresa': ['Empresa', 'Outra']}))
    provider = Mock(return_value={
        'indicadores': pd.DataFrame([dict(reclamacoes=2, tempo_medio=0, base_tempo=1, nota_media=None, base_nota=0)]),
        'mensal': pd.DataFrame({'mes': [7], 'reclamacoes': [2]}),
        'problemas': pd.DataFrame({'problema': ['Não informado'], 'reclamacoes': [2]}),
    })
    monkeypatch.setattr(companies, 'carregar_empresa', provider)
    monkeypatch.setattr(companies, 'comparar_empresas', lambda *args: pd.DataFrame({'mes': [7], 'empresa': ['Empresa'], 'reclamacoes': [2], 'total_mes': [4], 'participacao': [50]}))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'dashboard/app.py', default_timeout=10)
    app.session_state['dashboard_navigation'] = 'Empresas'
    return app, provider


def test_company_selection_and_missing_means(company_app):
    app, provider = company_app
    app.run()
    assert not app.exception
    assert app.subheader[0].value == 'Evolução mensal'
    assert [metric.value for metric in app.metric] == ['2', '0,00', 'N/D']
    assert len(app.get('plotly_chart')) == 1
    assert any(item.value == 'Principais problemas — até 10' for item in app.subheader)
    assert any('eci-problems-scroll' in item.proto.body for item in app.get('html'))
    assert any('class="eci-problem-bar"' in item.proto.body for item in app.get('html'))
    app.selectbox(key='companies_name').select('Outra').run()
    assert provider.call_args.args == (2026, [7], 'Outra')
    provider.reset_mock()
    app.multiselect(key='companies_months_2026').set_value([]).run()
    provider.assert_not_called()
    assert not app.metric


def test_company_failure_hides_details(company_app):
    app, provider = company_app
    provider.side_effect = RuntimeError('private-password')
    app.run()
    assert not app.exception
    assert app.error
    assert 'private-password' not in app.error[0].value


def test_company_comparison_switches_to_monthly_share(company_app):
    import json
    app, _ = company_app
    app.run()
    assert app.multiselect(key='companies_compare').max_selections == 3
    app.multiselect(key='companies_compare').set_value(['Empresa', 'Outra']).run()
    assert not app.exception
    app.radio(key='companies_measure').set_value('Participação no mês').run()
    figure = json.loads(app.get('plotly_chart')[0].proto.spec)
    assert len(figure['data']) == 2
    assert figure['layout']['yaxis']['ticksuffix'] == '%'
    assert figure['data'][0]['y'] == [50.0]
    app.multiselect(key='companies_compare').set_value([]).run()
    assert not app.exception
    assert any('Selecione de uma a três' in item.value for item in app.info)
