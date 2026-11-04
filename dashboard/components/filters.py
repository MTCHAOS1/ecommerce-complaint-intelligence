"""Filtros temporais da visão geral, limitados a meses com carga."""

import streamlit as st

from dashboard.constants import MESES


def meses_carregados(periodos, ano):
    return sorted(set(periodos.loc[periodos['ano'] == ano, 'mes'].astype(int)))


def render_filters(periodos, namespace='overview', titulo='visão geral'):
    anos = sorted(periodos['ano'].astype(int).unique().tolist(), reverse=True)
    with st.sidebar:
        st.header(f'Filtros de {titulo}')
        ano = st.selectbox('Ano', anos, key=f'{namespace}_year')
        disponiveis = meses_carregados(periodos, ano)
        meses = st.multiselect(
            'Meses carregados', options=disponiveis, default=disponiveis,
            format_func=lambda mes: MESES[mes], key=f'{namespace}_months_{ano}',
        )
        st.caption(f'Todos os KPIs e gráficos de {titulo} usam os meses selecionados.')
    return int(ano), sorted(meses)
