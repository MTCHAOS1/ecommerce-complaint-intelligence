"""Áreas, assuntos, grupos e problemas no mesmo recorte."""

import streamlit as st

from dashboard.components.analysis_page import preparar_pagina, erro_consulta, rodape
from dashboard.components.formatting import inteiro
from dashboard.components.presentation import ranking_completo
from dashboard.services.specialized import listar_areas, listar_assuntos, listar_grupos, carregar_problemas


def escolher(rotulo, valores, chave):
    opcoes = [None, *valores]
    if st.session_state.get(chave) not in opcoes:
        st.session_state[chave] = None
    return st.selectbox(rotulo, opcoes, format_func=lambda valor: 'Todos' if valor is None else valor, key=chave)


def render():
    recorte = preparar_pagina('Problemas', 'problems')
    if recorte is None:
        return
    try:
        areas = listar_areas(*recorte)
        area = st.selectbox('Área', [None, *areas['area'].tolist()], format_func=lambda valor: 'Todas as áreas' if valor is None else valor, key='problems_area')
        assuntos = listar_assuntos(*recorte, area=area)
        assunto = escolher('Assunto', assuntos['assunto'].tolist(), 'problems_subject')
        grupos = listar_grupos(*recorte, area=area, assunto=assunto)
        grupo = escolher('Grupo de problemas', grupos['grupo'].tolist(), 'problems_group')
        niveis = {'Áreas': 'areas', 'Assuntos': 'assuntos', 'Grupos de problemas': 'grupos', 'Problemas': 'problemas'}
        nivel = st.radio('Ranking principal', list(niveis), index=1, horizontal=True, key='problems_ranking')
        dados = carregar_problemas(*recorte, area=area, assunto=assunto, grupo=grupo, nivel=niveis[nivel])
    except Exception:
        erro_consulta()
        return
    kpis = dados['indicadores'].iloc[0]
    esquerda, direita = st.columns(2)
    esquerda.metric('Reclamações', inteiro(kpis['reclamacoes']))
    direita.metric('Áreas', inteiro(kpis['areas']))
    if not kpis['reclamacoes']:
        st.info('Não há registros para o recorte selecionado.')
        return
    st.caption('Espaços externos são removidos; nulos e vazios são agrupados em Não informado. Cada gráfico mostra até 15 categorias; suas barras podem não somar o total do recorte.')
    st.caption('Os nomes completos aparecem acima das barras. O comprimento de cada barra é relativo à maior contagem do respectivo ranking.')
    ranking_completo(dados[niveis[nivel]], niveis[nivel], nivel + ' — até 15')
    rodape()
