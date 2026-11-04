"""Rótulos completos, escape de conteúdo e identidade do estado de execução."""
from html.parser import HTMLParser

import pandas as pd
import pytest

pytest.importorskip('streamlit')
pytest.importorskip('plotly')
from dashboard.components.presentation import ranking_completo_html, estilos_loading, tabela_problemas_html


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.labels = []
        self.in_label = False

    def handle_starttag(self, tag, attrs):
        if tag == 'span' and ('class', 'eci-ranking-label') in attrs:
            self.in_label = True

    def handle_endtag(self, tag):
        if tag == 'span':
            self.in_label = False

    def handle_data(self, data):
        if self.in_label:
            self.labels.append(data)


def test_full_ranking_preserves_entire_subject_and_wraps_without_clipping():
    subject = 'Cobrança de valores não previstos em contrato e dificuldade para cancelamento do serviço ' * 5
    html = ranking_completo_html(pd.DataFrame({'assuntos': [subject], 'reclamacoes': [1234]}), 'assuntos', 'Assuntos')
    text = VisibleText()
    text.feed(html)
    assert text.labels == [subject]
    assert '1.234' in html
    assert 'overflow-wrap: anywhere' in html
    assert 'white-space: normal' in html
    assert 'text-overflow' not in html
    assert 'width:100.0000%' in html


def test_full_ranking_escapes_labels_and_orders_by_count_then_name():
    html = ranking_completo_html(pd.DataFrame({'assuntos': ['B', '<script>alert("x")</script>', 'A'],
                                              'reclamacoes': [2, 5, 2]}), 'assuntos', 'Assuntos')
    assert '<script>' not in html
    text = VisibleText()
    text.feed(html)
    assert text.labels == ['<script>alert("x")</script>', 'A', 'B']
    assert 'width:40.0000%' in html


def test_zero_ranking_does_not_divide_by_zero():
    html = ranking_completo_html(pd.DataFrame({'assuntos': ['Sem volume'], 'reclamacoes': [0]}), 'assuntos', 'Assuntos')
    assert 'width:0.0000%' in html
    table = tabela_problemas_html(pd.DataFrame({'problema': ['Sem volume'], 'reclamacoes': [0]}))
    assert 'width:0.0000%' in table


def test_loading_style_targets_only_running_icon_and_respects_reduced_motion():
    css = estilos_loading()
    assert '[data-testid="stStatusWidgetRunningIcon"]' in css
    assert 'data:image/svg+xml,' in css
    assert 'prefers-reduced-motion: reduce' in css
    assert 'stToolbar' not in css
    assert 'stStatusWidgetRunningIcon"] > svg' in css
    assert 'animation: none' in css


def test_problem_table_limits_to_top_ten_and_preserves_complete_safe_text():
    description = '<script>alert("x")</script> ' + 'Descrição completa do problema ' * 30
    frame = pd.DataFrame({
        'problema': [f'Problema {i:02d}' for i in range(12)] + [description],
        'reclamacoes': list(range(12)) + [1234],
    })
    html = tabela_problemas_html(frame)
    assert html.count('<tr>') == 11  # Cabeçalho e dez problemas.
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'Descrição completa do problema ' * 30 in html
    assert '1.234' in html
    assert 'Problema 00' not in html
    assert 'Problema 02' not in html
    assert html.index('1.234') < html.index('Problema 11') < html.index('Problema 10')
    assert 'overflow: auto' in html
    assert 'white-space: normal' in html
    assert 'position: sticky' in html
    assert 'tabindex="0"' in html
    assert html.count('class="eci-problem-bar"') == 10
    assert 'Quantidade de reclamações' in html
    assert 'Classificação do problema' in html
    assert 'eci-problem-position' not in html
    assert 'width:100.0000%' in html
    assert f'width:{100 * 11 / 1234:.4f}%' in html
    assert 'aria-hidden="true"' in html
