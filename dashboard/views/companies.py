import streamlit as st

from dashboard.components.filters import render_filters
from dashboard.components.formatting import inteiro, media
from dashboard.components.monthly import figura_comparacao
from dashboard.components.presentation import tabela_problemas
from dashboard.constants import MESES
from dashboard.services.analytics import consultar_lote, periodos_disponiveis
from dashboard.services.companies import carregar_empresa, listar_empresas, comparar_empresas


def render():
    st.header("Empresas")
    st.caption('Nomes fantasia normalizados, agrupando segmentos do mesmo nome; não representa CNPJs distintos.')
    with st.sidebar:
        if st.button('Atualizar dados', key='companies_refresh'):
            consultar_lote.clear()
    try:
        periodos = periodos_disponiveis()
        if periodos.empty:
            st.warning('Nenhum período foi carregado na Gold.')
            return
        ano, meses = render_filters(periodos, 'companies', 'empresas')
        if not meses:
            st.info('Selecione pelo menos um mês.')
            return
        empresas = listar_empresas(ano, meses)
        if empresas.empty:
            st.info('Nenhuma empresa encontrada no recorte selecionado.')
            return
        empresa = st.selectbox('Empresa (nome fantasia)', empresas['empresa'].tolist(), key='companies_name')
        opcoes_comparacao = empresas['empresa'].tolist()
        if 'companies_compare' in st.session_state:
            validas = [e for e in st.session_state['companies_compare'] if e in opcoes_comparacao]
            if validas != st.session_state['companies_compare']:
                st.session_state['companies_compare'] = validas
        selecionadas = st.multiselect('Comparar até três empresas', empresas['empresa'].tolist(),
                                       default=[empresa], max_selections=3, key='companies_compare')
        comparacao = comparar_empresas(ano, meses, selecionadas) if selecionadas else None
        dados = carregar_empresa(ano, meses, empresa)
    except Exception:
        st.error('Não foi possível carregar as empresas. Verifique a conexão com o banco e tente novamente.')
        return
    st.caption(f'Recorte por data de finalização: {ano} — ' + ', '.join(MESES[m] for m in meses))
    indicadores = dados['indicadores'].iloc[0]
    with st.container(border=True):
        st.subheader('Evolução mensal')
        if selecionadas:
            medida = st.radio('Comparar por', ['Volume', 'Participação no mês'], horizontal=True,
                              key='companies_measure')
            st.plotly_chart(figura_comparacao(comparacao, meses, selecionadas, medida != 'Volume'),
                            width='stretch', key='companies_comparison_chart')
            st.caption('Participação = reclamações da empresa / total de reclamações da Gold no mês, incluindo todas as empresas e setores. Não é taxa por cliente ou venda. Lacunas não são conectadas; ausência de registros não é preenchida com zero.')
        else:
            st.info('Selecione de uma a três empresas para comparar.')
    st.caption(f'Indicadores e problemas abaixo: {empresa}.')
    st.subheader('Resumo do recorte')
    st.metric('Reclamações', inteiro(indicadores['reclamacoes']))
    esquerda, direita = st.columns(2)
    with esquerda:
        st.metric('Tempo médio de resposta', media(indicadores['tempo_medio']))
        st.caption(f"Base: {inteiro(indicadores['base_tempo'])} reclamações com tempo informado. Unidade registrada na fonte.")
    with direita:
        st.metric('Nota média informada (1 a 5)', media(indicadores['nota_media']))
        st.caption(f"Base: {inteiro(indicadores['base_nota'])} reclamações com nota informada.")
    st.caption('Médias usam valores preenchidos, independentemente do rótulo de avaliação. N/D indica ausência de valores. Volumes não medem taxas por cliente ou venda.')
    if not indicadores['reclamacoes']:
        st.info('Não há registros para a empresa no recorte. Atualize os dados.')
        return
    tabela_problemas(dados['problemas'])
    st.caption('Meses sem carga não são oferecidos. Meses sem registros da empresa não recebem barras de zero. Cache: 10 minutos.')
