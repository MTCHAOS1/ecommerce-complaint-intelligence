"""Elementos compartilhados das páginas especializadas."""

import streamlit as st

from dashboard.components.charts import ranking
from dashboard.components.filters import meses_carregados, render_filters
from dashboard.constants import MESES
from dashboard.services.analytics import consultar_lote, periodos_disponiveis


def preparar_pagina(titulo, namespace):
    st.header(titulo)
    with st.sidebar:
        if st.button('Atualizar dados', key=f'{namespace}_refresh'):
            consultar_lote.clear()
    try:
        periodos = periodos_disponiveis()
    except Exception:
        erro_consulta()
        return None
    if periodos.empty:
        st.warning('Nenhum período foi carregado na Gold.')
        return None
    ano, meses = render_filters(periodos, namespace, titulo.lower())
    ausentes = [MESES[m] for m in MESES if m not in meses_carregados(periodos, ano)]
    if ausentes:
        st.info(f'Meses sem dados carregados em {ano}: ' + ', '.join(ausentes) + '. Ausência de carga não representa zero reclamações.')
    if not meses:
        st.info('Selecione pelo menos um mês.')
        return None
    st.caption(f'Recorte por data de finalização: {ano} — ' + ', '.join(MESES[m] for m in meses))
    return ano, meses


def erro_consulta():
    st.error('Não foi possível carregar os indicadores. Verifique a conexão com o banco e tente novamente.')


def barras(dados, categoria, titulo):
    st.subheader(titulo)
    st.plotly_chart(ranking(dados, categoria, ''), width='stretch', key=f'ranking_{categoria}')


def rodape():
    st.caption('Fonte: Consumidor.gov.br. Volumes não medem taxas por cliente, venda ou população. Meses sem registros não recebem barras de zero. Consultas somente leitura; cache de dez minutos.')
