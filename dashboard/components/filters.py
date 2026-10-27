"""Filtros temporais da visão geral, limitados a meses com carga."""
import streamlit as st

from dashboard.services.overview import MESES


def meses_carregados(periodos, ano):
    return sorted(set(periodos.loc[periodos['ano'] == ano, 'mes'].astype(int)))


def render_filters(periodos):
    anos = sorted(periodos['ano'].astype(int).unique().tolist(), reverse=True)
    with st.sidebar:
        st.header('Filtros da visão geral')
        ano = st.selectbox('Ano', anos, key='overview_year')
        disponiveis = meses_carregados(periodos, ano)
        meses = st.multiselect(
            'Meses carregados', options=disponiveis, default=disponiveis,
            format_func=lambda mes: MESES[mes], key=f'overview_months_{ano}',
        )
        st.caption('Todos os KPIs e gráficos da visão geral usam os meses selecionados.')
    return int(ano), sorted(meses)
