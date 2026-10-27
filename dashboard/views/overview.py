"""Visão geral: definições explícitas e um recorte para todos os gráficos."""
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.filters import meses_carregados, render_filters
from dashboard.services.analytics import consultar_lote, periodos_disponiveis
from dashboard.services.overview import MESES, carregar_visao_geral


def inteiro(value):
    return f'{int(value):,}'.replace(',', '.')


def media(value):
    return f'{float(value):.2f}'.replace('.', ',') if pd.notna(value) else 'N/D'


def render():
    st.title('E-commerce Complaint Intelligence')
    st.caption('Reclamações públicas do Consumidor.gov.br de diferentes setores, considerando a data de finalização.')
    with st.sidebar:
        if st.button('Atualizar dados', key='overview_refresh'):
            consultar_lote.clear()
    try:
        periodos = periodos_disponiveis()
    except Exception:
        st.error('Não foi possível consultar os períodos. Verifique a conexão com o banco e tente novamente.')
        return
    if periodos.empty:
        st.warning('Nenhum período foi carregado na Gold.')
        return

    ano, meses = render_filters(periodos)
    ausentes = [MESES[mes] for mes in MESES if mes not in meses_carregados(periodos, ano)]
    if ausentes:
        st.info(f'Meses sem dados carregados em {ano}: ' + ', '.join(ausentes) + '. Ausência de carga não representa zero reclamações.')
    if not meses:
        st.info('Selecione pelo menos um mês.')
        return

    st.caption(f'Recorte: {ano} — ' + ', '.join(MESES[mes] for mes in meses) + '.')
    try:
        dados = carregar_visao_geral(ano, meses)
    except Exception:
        st.error('Não foi possível carregar os indicadores. Verifique a conexão com o banco e tente novamente.')
        return
    indicadores = dados['indicadores'].iloc[0]
    st.subheader('Visão geral')
    col1, col2, col3 = st.columns(3)
    col1.metric('Reclamações', inteiro(indicadores['reclamacoes']), help='Quantidade de registros na Gold para as datas de finalização selecionadas.')
    col2.metric('Empresas (nome fantasia)', inteiro(indicadores['empresas']), help='Nomes fantasia distintos após remover espaços nas extremidades, agrupando segmentos do mesmo nome. É a mesma definição usada no ranking; não é uma contagem de CNPJs.')
    col3.metric('UFs', inteiro(indicadores['ufs']), help='Unidades federativas com reclamações no recorte, incluindo o Distrito Federal.')
    col4, col5 = st.columns(2)
    with col4:
        st.metric('Tempo médio de resposta', media(indicadores['tempo_medio']), help='Média dos tempos preenchidos. Valores ausentes não são tratados como zero. A unidade é a registrada na fonte.')
        st.caption(f"Base: {inteiro(indicadores['base_tempo'])} reclamações com tempo informado.")
    with col5:
        st.metric('Nota média informada (1 a 5)', media(indicadores['nota_media']), help='Média das notas preenchidas, independentemente do rótulo de avaliação. Valores ausentes não são tratados como zero.')
        st.caption(f"Base: {inteiro(indicadores['base_nota'])} reclamações com nota informada.")
    st.caption('O tempo é exibido na unidade registrada na fonte. N/D indica ausência de valores para calcular a média.')
    if int(indicadores['reclamacoes']) == 0:
        st.info('Não há registros para o recorte selecionado. Atualize os dados e confira os períodos disponíveis.')
        return

    st.divider()
    mensal = dados['mensal'].copy()
    mensal['nome_mes'] = mensal['mes'].map(MESES)
    st.subheader('Evolução mensal — meses selecionados')
    fig = px.bar(mensal, x='nome_mes', y='reclamacoes',
                 category_orders={'nome_mes': [MESES[mes] for mes in meses]},
                 labels={'nome_mes': 'Mês de finalização', 'reclamacoes': 'Reclamações'})
    st.plotly_chart(fig, width='stretch')

    col_esq, col_dir = st.columns(2)
    with col_esq:
        st.subheader('Nomes de empresas com mais reclamações — até 15')
        empresas = dados['empresas'].sort_values(['reclamacoes', 'empresa'], ascending=[True, False])
        fig = px.bar(empresas, x='reclamacoes', y='empresa', orientation='h',
                     labels={'empresa': 'Nome fantasia', 'reclamacoes': 'Reclamações'})
        st.plotly_chart(fig, width='stretch')
    with col_dir:
        st.subheader('Reclamações por UF')
        fig = px.bar(dados['estados'], x='uf', y='reclamacoes',
                     labels={'uf': 'UF', 'reclamacoes': 'Reclamações'})
        st.plotly_chart(fig, width='stretch')
    st.subheader('Principais áreas de reclamação — até 15')
    areas = dados['areas'].sort_values(['reclamacoes', 'area'], ascending=[True, False])
    fig = px.bar(areas, x='reclamacoes', y='area', orientation='h',
                 labels={'area': 'Área', 'reclamacoes': 'Reclamações'})
    st.plotly_chart(fig, width='stretch')
    st.caption('Os rankings mostram volumes de registros no recorte; não medem taxa de reclamação por cliente ou venda.')
    st.divider()
    st.caption('Fonte: Consumidor.gov.br | Data de finalização | Consultas somente leitura | Cache: 10 minutos')
