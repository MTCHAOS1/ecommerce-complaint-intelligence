"""Navegação, filtros e estados de erro das três páginas especializadas."""
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

pytest.importorskip('streamlit')
pytest.importorskip('plotly')
from streamlit.testing.v1 import AppTest
from dashboard.components import analysis_page
from dashboard.views import geography, problems, service


@pytest.fixture(params=[('Geografia', geography, 'carregar_geografia', 4),
                        ('Problemas', problems, 'carregar_problemas', 0),
                        ('Atendimento', service, 'carregar_atendimento', 3)])
def specialized_app(request, monkeypatch):
    title, module, loader, plots = request.param
    periods = pd.DataFrame({'ano': [2025, 2026, 2026], 'mes': [2, 7, 8]})
    monkeypatch.setattr(analysis_page, 'periodos_disponiveis', lambda: periods)
    monkeypatch.setattr(problems, 'listar_areas', lambda *args: pd.DataFrame({'area': ['Financeiro']}))
    monkeypatch.setattr(problems, 'listar_assuntos', lambda *args, **kwargs: pd.DataFrame({'assunto': ['Não informado']}))
    monkeypatch.setattr(problems, 'listar_grupos', lambda *args, **kwargs: pd.DataFrame({'grupo': ['Não informado']}))
    indicators = dict(reclamacoes=2, ufs=1, cidades=1, areas=1, tempo_medio=0,
                      base_tempo=1, nota_media=None, base_nota=0, respondidas=0,
                      base_respondida=0, percentual_respondidas=None)
    data = {'indicadores': pd.DataFrame([indicators]),
            'mensal': pd.DataFrame([dict(mes=7, **indicators)]),
            'estados': pd.DataFrame({'uf': ['SP'], 'reclamacoes': [2]}),
            'cidades': pd.DataFrame({'cidade': ['São Paulo / SP'], 'reclamacoes': [2]}),
            'avaliacoes': pd.DataFrame({'avaliacao': ['Não informado'], 'reclamacoes': [2]}),
            'notas': pd.DataFrame(columns=['nota', 'reclamacoes'])}
    for name in ('areas', 'assuntos', 'grupos', 'problemas'):
        data[name] = pd.DataFrame({name: ['Não informado'], 'reclamacoes': [2]})
    provider = Mock(return_value=data)
    monkeypatch.setattr(module, loader, provider)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'dashboard/app.py', default_timeout=10)
    app.session_state['dashboard_navigation'] = title
    return app, provider, plots, module


def test_specialized_filters_and_charts(specialized_app):
    app, provider, plots, module = specialized_app
    app.run()
    assert not app.exception
    assert app.metric[0].value == '2'
    if module is not problems:
        assert app.subheader[0].value == 'Evolução mensal'
    assert len(app.get('plotly_chart')) == plots
    assert provider.call_args.args == (2026, [7, 8])
    app.multiselect[0].set_value([8]).run()
    assert provider.call_args.args == (2026, [8])
    if module is geography:
        app.selectbox(key='geography_uf').select('DF').run()
        assert provider.call_args.kwargs == {'uf': 'DF'}
    if module is problems:
        app.selectbox(key='problems_area').select('Financeiro').run()
        assert provider.call_args.kwargs == {'area': 'Financeiro', 'assunto': None, 'grupo': None, 'nivel': 'assuntos'}
    if module is service:
        assert app.metric[1].value == 'N/D'
        assert app.metric[2].value == '0,00'
        assert app.metric[3].value == 'N/D'
    provider.reset_mock()
    app.multiselect[0].set_value([]).run()
    provider.assert_not_called()
    assert not app.metric
    assert not app.get('plotly_chart')


def test_specialized_year_switch_and_refresh(specialized_app, monkeypatch):
    app, provider, _, module = specialized_app
    clear = Mock()
    monkeypatch.setattr(analysis_page.consultar_lote, 'clear', clear)
    app.run()
    namespace = {geography: 'geography', problems: 'problems', service: 'service'}[module]
    app.selectbox(key=f'{namespace}_year').select(2025).run()
    assert provider.call_args.args == (2025, [2])
    app.button(key=f'{namespace}_refresh').click().run()
    clear.assert_called_once()


def test_specialized_empty_and_error_states(specialized_app, monkeypatch):
    app, provider, _, _ = specialized_app
    provider.side_effect = RuntimeError('private-connection')
    app.run()
    assert not app.exception
    assert app.error
    assert 'private-connection' not in app.error[0].value
    monkeypatch.setattr(analysis_page, 'periodos_disponiveis', lambda: pd.DataFrame())
    provider.reset_mock()
    app.run()
    provider.assert_not_called()
    assert app.warning
    assert not app.metric


@pytest.mark.parametrize('specialized_app', [('Geografia', geography, 'carregar_geografia', 4)], indirect=True)
def test_geography_offers_map_and_uf_bars_below_monthly_trend(specialized_app):
    import json
    app, _, _, module = specialized_app
    app.run()
    figures = [json.loads(chart.proto.spec) for chart in app.get('plotly_chart')]
    assert figures[0]['data'][0]['type'] == 'scatter'
    figure = figures[2]
    assert [trace['type'] for trace in figure['data']] == ['choroplethmap', 'choroplethmap']
    assert figure['data'][1]['customdata'][0][0] == 'SP'
    assert [tab.label for tab in app.tabs] == ['Barras', 'Mapa']
    assert figures[1]['data'][0]['orientation'] == 'h'
    assert any('IBGE' in caption.value for caption in app.caption)
    assert app.expander[0].label == 'Comparar valores exatos por UF'


@pytest.mark.parametrize('specialized_app', [('Atendimento', service, 'carregar_atendimento', 3)], indirect=True)
def test_service_renders_notes_as_ordered_bars(specialized_app):
    import json
    app, provider, _, module = specialized_app
    data = provider.return_value.copy()
    data['notas'] = pd.DataFrame({'nota': [1, 5], 'reclamacoes': [1, 1]})
    provider.return_value = data
    app.run()
    assert not app.exception
    assert len(app.get('plotly_chart')) == 4
    figure = json.loads(app.get('plotly_chart')[-1].proto.spec)
    assert figure['data'][0]['x'] == [1, 2, 3, 4, 5]
    assert figure['data'][0]['y'] == [1, 0, 0, 0, 1]


@pytest.mark.parametrize('specialized_app', [('Atendimento', service, 'carregar_atendimento', 3)], indirect=True)
def test_service_shows_aligned_monthly_indicators_with_missing_base(specialized_app):
    import json
    app, provider, _, _ = specialized_app
    app.run()
    first = json.loads(app.get('plotly_chart')[0].proto.spec)
    assert first['data'][0]['type'] == 'scatter'
    assert first['layout']['yaxis']['title']['text'] == 'Reclamações'
    time_figure = json.loads(app.get('plotly_chart')[1].proto.spec)
    assert time_figure['data'][0]['y'] == [0.0, None]
    assert time_figure['layout']['yaxis']['title']['text'] == 'Tempo médio de resposta'
    assert len([info for info in app.info if 'Sem valores informados' in info.value]) == 2
    assert any(exp.label == 'Detalhes mensais — médias e bases' for exp in app.expander)


@pytest.mark.parametrize('specialized_app', [('Problemas', problems, 'carregar_problemas', 0)], indirect=True)
def test_problem_subjects_are_fully_visible_without_hover(specialized_app):
    from html import escape
    app, provider, _, _ = specialized_app
    subject = 'Cobrança indevida por serviço não contratado e dificuldade para cancelamento ' * 6
    provider.return_value['assuntos'] = pd.DataFrame({'assuntos': [subject], 'reclamacoes': [2]})
    app.run()
    assert not app.exception
    rankings = [item.proto.body for item in app.get('html') if 'class="eci-full-ranking"' in item.proto.body]
    assert len(rankings) == 1
    assert escape(subject) in rankings[0]
    assert any('stStatusWidgetRunningIcon' in item.proto.body for item in app.get('html'))
    assert not app.get('plotly_chart')


@pytest.mark.parametrize('specialized_app', [('Problemas', problems, 'carregar_problemas', 0)], indirect=True)
def test_problem_navigation_filters_hierarchy_and_shows_one_ranking(specialized_app):
    app, provider, _, _ = specialized_app
    app.run()
    app.selectbox(key='problems_area').select('Financeiro').run()
    app.selectbox(key='problems_subject').select('Não informado').run()
    app.selectbox(key='problems_group').select('Não informado').run()
    app.radio(key='problems_ranking').set_value('Problemas').run()
    assert not app.exception
    assert provider.call_args.kwargs == {'area': 'Financeiro', 'assunto': 'Não informado',
                                         'grupo': 'Não informado', 'nivel': 'problemas'}
    rankings = [item for item in app.get('html') if 'class="eci-full-ranking"' in item.proto.body]
    assert len(rankings) == 1


@pytest.mark.parametrize('specialized_app', [('Atendimento', service, 'carregar_atendimento', 3)], indirect=True)
def test_service_displays_all_three_quality_series_at_once(specialized_app):
    import json
    app, provider, _, _ = specialized_app
    monthly = provider.return_value['mensal'].copy()
    monthly['nota_media'] = 3
    monthly['base_nota'] = 2
    monthly['percentual_respondidas'] = 50
    monthly['base_respondida'] = 2
    provider.return_value['mensal'] = monthly
    app.run()
    assert not app.exception
    figures = [json.loads(item.proto.spec) for item in app.get('plotly_chart')]
    assert [f['layout']['yaxis']['title']['text'] for f in figures[:4]] == [
        'Reclamações', 'Tempo médio de resposta', 'Nota média', 'Respondidas (%)']
    assert figures[2]['data'][0]['y'] == [3.0, None]
    assert figures[3]['data'][0]['y'] == [50.0, None]
    assert figures[2]['data'][0]['customdata'][0][2] == 'Base: 2 registros informados'
    assert figures[3]['layout']['yaxis']['range'] == [0, 110]
