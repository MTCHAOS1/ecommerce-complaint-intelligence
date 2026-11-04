"""A série mensal preserva lacunas, zeros, unidades e denominadores."""
import pandas as pd
import pytest

pytest.importorskip('streamlit')
pytest.importorskip('plotly')
from dashboard.components.monthly import figura_mensal


def test_monthly_series_keeps_calendar_gaps_and_does_not_invent_zero():
    data = pd.DataFrame({'mes': [1, 3], 'reclamacoes': [100, 300]})
    figure = figura_mensal(data, [1, 3])
    trace = figure.data[0]
    assert list(trace.x) == ['Janeiro', 'Fevereiro', 'Março']
    assert list(trace.y) == [100, None, 300]
    assert trace.connectgaps is False
    assert 'Sem comparação' in trace.customdata[2][1]
    assert figure.layout.height >= 400


def test_variation_uses_previous_calendar_month_and_preserves_zero():
    data = pd.DataFrame({'mes': [1, 2, 3], 'reclamacoes': [100, 0, 200]})
    trace = figura_mensal(data, [1, 2, 3]).data[0]
    assert trace.y[1] == 0
    assert trace.text[1] == '0'
    assert trace.customdata[1][1] == '-100,00% ante o mês anterior'
    assert 'Sem comparação' in trace.customdata[2][1]


def test_response_variation_is_in_percentage_points_with_reported_base():
    data = pd.DataFrame({'mes': [7, 8], 'percentual_respondidas': [50, 75], 'base_respondida': [4, 8]})
    figure = figura_mensal(data, [7, 8], 'Respondidas (%)')
    trace = figure.data[0]
    assert trace.text[1] == '75,00%'
    assert trace.customdata[1][1] == '+25,00 p.p. ante o mês anterior'
    assert trace.customdata[1][2] == 'Base: 8 registros informados'
    assert figure.layout.yaxis.range == (0, 110)


def test_score_series_preserves_missing_mean_and_uses_score_units():
    data = pd.DataFrame({'mes': [1, 2, 3], 'nota_media': [2, 3, None], 'base_nota': [5, 6, 0]})
    figure = figura_mensal(data, [1, 2, 3], 'Nota média')
    trace = figure.data[0]
    assert trace.customdata[1][1] == '+1,00 pontos ante o mês anterior'
    assert trace.y[2] is None
    assert figure.layout.yaxis.range == (0, 5.6)


def test_single_selected_month_is_visible_without_comparison():
    trace = figura_mensal(pd.DataFrame({'mes': [9], 'reclamacoes': [1200]}), [9]).data[0]
    assert list(trace.x) == ['Setembro']
    assert list(trace.text) == ['1.200']
    assert 'markers' in trace.mode
    assert 'Sem comparação' in trace.customdata[0][1]


def test_monthly_columns_preserve_gaps_and_observed_zero():
    figure = figura_mensal(pd.DataFrame({'mes': [1, 3], 'reclamacoes': [0, 100]}), [1, 3], formato='Colunas')
    assert figure.data[0].type == 'bar'
    assert list(figure.data[0].y) == [0, None, 100]
    assert figure.data[0].text[0] == '0'


def test_company_comparison_preserves_gaps_and_percentage_unit():
    from dashboard.components.monthly import figura_comparacao
    data = pd.DataFrame({'mes': [1, 3], 'empresa': ['A', 'A'], 'reclamacoes': [5, 10],
                         'total_mes': [20, 40], 'participacao': [25, 25]})
    figure = figura_comparacao(data, [1, 3], ['A', 'B'], participacao=True)
    assert list(figure.data[0].y) == [25, None, 25]
    assert list(figure.data[1].y) == [None, None, None]
    assert figure.data[0].connectgaps is False
    assert figure.data[0].customdata[0][1] == '20'
    assert figure.layout.yaxis.ticksuffix == '%'
