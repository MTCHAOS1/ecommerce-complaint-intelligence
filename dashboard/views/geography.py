"""Distribuição por UF e cidade, incluindo Distrito Federal."""

import streamlit as st

from dashboard.components.analysis_page import preparar_pagina, erro_consulta, barras, rodape
from dashboard.components.charts import mapa_ufs
from dashboard.components.formatting import inteiro
from dashboard.components.monthly import evolucao
from dashboard.services.specialized import UFS, carregar_geografia


def render():
    recorte = preparar_pagina('Geografia', 'geography')
    if recorte is None:
        return
    uf = st.selectbox('UF', [None, *UFS], format_func=lambda valor: valor or 'Todas as UFs', key='geography_uf')
    try:
        dados = carregar_geografia(*recorte, uf=uf)
    except Exception:
        erro_consulta()
        return
    kpis = dados['indicadores'].iloc[0]
    if kpis['reclamacoes']:
        evolucao(dados['mensal'], recorte[1], 'geography')
    st.subheader('Resumo do recorte')
    for coluna, campo, rotulo in zip(st.columns(3), ['reclamacoes', 'ufs', 'cidades'], ['Reclamações', 'UFs', 'Cidades (cidade e UF)']):
        coluna.metric(rotulo, inteiro(kpis[campo]))
    if not kpis['reclamacoes']:
        st.info('Não há registros para o recorte selecionado.')
        return
    st.caption('Cidades são identificadas pelo nome com espaços externos removidos e pela UF; nomes iguais em UFs diferentes são separados. DF está incluído.')
    st.subheader('Comparação por UF')
    grafico, mapa = st.tabs(['Barras', 'Mapa'])
    with grafico:
        barras(dados['estados'], 'uf', 'Reclamações por UF')
    with mapa:
        st.plotly_chart(mapa_ufs(dados['estados'], uf), width='stretch', key='geography_map')
    st.caption('Estados com azul mais intenso têm mais reclamações no recorte. A escala representa volume absoluto e é recalculada para o recorte; não é uma taxa por população. Passe o cursor para valores e participação. Cinza: sem registros ou fora do filtro de UF. Malha simplificada: IBGE. Use zoom para inspecionar o DF.')
    with st.expander('Comparar valores exatos por UF'):
        st.dataframe(dados['estados'].sort_values(['reclamacoes', 'uf'], ascending=[False, True]).rename(columns={'uf': 'UF', 'reclamacoes': 'Reclamações'}), hide_index=True)
    barras(dados['cidades'], 'cidade', 'Cidades com mais reclamações — até 15')
    rodape()
