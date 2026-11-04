"""Indicadores de resposta e notas com denominadores explícitos."""

import streamlit as st

from dashboard.components.analysis_page import preparar_pagina, erro_consulta, barras, rodape
from dashboard.components.charts import distribuicao_notas
from dashboard.components.formatting import inteiro, media
from dashboard.components.monthly import atendimento_mensal
from dashboard.constants import MESES
from dashboard.services.specialized import carregar_atendimento


def render():
    recorte = preparar_pagina('Atendimento', 'service')
    if recorte is None:
        return
    try:
        dados = carregar_atendimento(*recorte)
    except Exception:
        erro_consulta()
        return
    kpis = dados['indicadores'].iloc[0]
    if kpis['reclamacoes']:
        atendimento_mensal(dados['mensal'], recorte[1])
    st.subheader('Resumo do recorte')
    esquerda, direita = st.columns(2)
    esquerda.metric('Reclamações', inteiro(kpis['reclamacoes']))
    direita.metric('Respondidas entre registros informados', media(kpis['percentual_respondidas']) + ('%' if kpis['base_respondida'] else ''))
    st.caption(f"Base de resposta: {inteiro(kpis['base_respondida'])}; respondidas: {inteiro(kpis['respondidas'])}. Booleanos ausentes são excluídos do denominador. Resposta não indica resolução.")
    esquerda, direita = st.columns(2)
    esquerda.metric('Tempo médio de resposta', media(kpis['tempo_medio']))
    direita.metric('Nota média informada (1 a 5)', media(kpis['nota_media']))
    st.caption(f"Bases: {inteiro(kpis['base_tempo'])} tempos e {inteiro(kpis['base_nota'])} notas preenchidos. Tempo na unidade da fonte. Médias excluem nulos; notas independem do rótulo de avaliação. N/D indica base ausente.")
    if not kpis['reclamacoes']:
        st.info('Não há registros para o recorte selecionado.')
        return
    with st.expander('Detalhes mensais — médias e bases'):
        st.subheader('Atendimento por mês — médias e bases')
        mensal = dados['mensal'].copy()
        mensal['mes'] = mensal['mes'].map(MESES)
        st.dataframe(mensal.rename(columns={'mes': 'Mês', 'reclamacoes': 'Reclamações', 'tempo_medio': 'Tempo médio', 'base_tempo': 'Base de tempos', 'nota_media': 'Nota média', 'base_nota': 'Base de notas', 'respondidas': 'Respondidas', 'base_respondida': 'Base de resposta', 'percentual_respondidas': 'Respondidas (%)'}), hide_index=True)
    barras(dados['avaliacoes'], 'avaliacao', 'Avaliação da reclamação')
    st.subheader('Distribuição das notas preenchidas')
    if dados['notas'].empty:
        st.info('Não há notas preenchidas no recorte selecionado.')
    else:
        st.plotly_chart(distribuicao_notas(dados['notas']), width='stretch')
        st.caption('Notas de 1 a 5. Zero indica ausência daquela nota entre os registros do recorte; notas ausentes não entram na distribuição.')
    rodape()
