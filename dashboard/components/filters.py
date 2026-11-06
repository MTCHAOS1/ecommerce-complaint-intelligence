"""Filtros temporais da visão geral, limitados a meses com carga."""

from datetime import date
from zoneinfo import ZoneInfo

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
        chave = f'{namespace}_months_{ano}'
        todos, recentes, limpar = st.columns(3)
        if todos.button('Todos', key=f'{namespace}_all'):
            st.session_state[chave] = disponiveis
        if recentes.button('3 meses', key=f'{namespace}_recent', help='Três últimos meses carregados no ano.'):
            st.session_state[chave] = disponiveis[-3:]
        if limpar.button('Limpar', key=f'{namespace}_clear'):
            st.session_state[chave] = []
        meses = st.multiselect(
            'Meses carregados', options=disponiveis, default=disponiveis,
            format_func=lambda mes: MESES[mes], key=f'{namespace}_months_{ano}',
        )
        st.caption(f'Todos os KPIs e gráficos de {titulo} usam os meses selecionados.')
    return int(ano), sorted(meses)


def cobertura(periodos, ano, today=None):
    """Distingue lacunas em meses encerrados de meses ainda abertos/futuros."""
    today = today or date.today()
    carregados = meses_carregados(periodos, ano)
    ausentes = [m for m in MESES if m not in carregados and (ano, m) < (today.year, today.month)]
    abertos = [m for m in MESES if m not in carregados and (ano, m) >= (today.year, today.month)]
    return ausentes, abertos


def mostrar_cobertura(periodos, ano):
    ultimo = periodos.sort_values(['ano', 'mes']).iloc[-1]
    texto = f"Dados até {MESES[int(ultimo['mes'])].lower()}/{int(ultimo['ano'])}"
    if 'ultima_carga' in periodos and periodos['ultima_carga'].notna().any():
        ultima = periodos['ultima_carga'].dropna().max().astimezone(ZoneInfo('America/Sao_Paulo'))
        texto += f" · Última carga bem-sucedida: {ultima:%d/%m/%Y %Hh%M} (Brasília)"
    st.caption(texto)
    if 'registros_invalidos' in periodos and periodos['registros_invalidos'].sum():
        invalidos = periodos[periodos['registros_invalidos'] > 0]
        with st.expander('Qualidade dos dados históricos'):
            st.warning(f"{int(invalidos['registros_invalidos'].sum())} registros com nota ou tempo de resposta fora do domínio. Os registros históricos e os indicadores foram preservados; considere essa limitação ao interpretar as médias.")
            st.dataframe(invalidos[['ano', 'mes', 'registros_invalidos']].rename(columns={
                'ano': 'Ano', 'mes': 'Mês', 'registros_invalidos': 'Registros inválidos'}), hide_index=True)
    ausentes, abertos = cobertura(periodos, ano)
    if ausentes:
        st.info(f'Meses encerrados sem dados carregados em {ano}: ' + ', '.join(MESES[m] for m in ausentes) + '. Ausência de carga não representa zero reclamações.')
    if abertos:
        st.caption('Meses ainda não encerrados: ' + ', '.join(MESES[m] for m in abertos) + '.')


def resumo_recorte(ano, meses):
    if len(meses) > 1 and meses == list(range(min(meses), max(meses) + 1)):
        return f'{MESES[min(meses)]} a {MESES[max(meses)]}/{ano}'
    return f'{ano} · ' + ', '.join(MESES[m] for m in meses)
