"""Evolução mensal em destaque, com lacunas e bases explícitas."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.charts import numero
from dashboard.constants import MESES


INDICADORES = {
    'Reclamações': ('reclamacoes', None, 'volume'),
    'Tempo médio de resposta': ('tempo_medio', 'base_tempo', 'media'),
    'Nota média': ('nota_media', 'base_nota', 'nota'),
    'Respondidas (%)': ('percentual_respondidas', 'base_respondida', 'percentual'),
}


def formatar(valor, tipo):
    if pd.isna(valor):
        return 'N/D'
    if tipo == 'volume':
        return numero(valor)
    return f'{float(valor):.2f}'.replace('.', ',') + ('%' if tipo == 'percentual' else '')


def preparar_serie(dados, meses, campo):
    """Meses ausentes mantêm posição cronológica sem ganhar valor zero."""
    selecionados = sorted(set(meses))
    serie = dados.set_index('mes').reindex(range(min(selecionados), max(selecionados) + 1)).copy()
    serie.index.name = 'mes'
    serie.loc[~serie.index.isin(selecionados), campo] = float('nan')
    return serie


def figura_mensal(dados, meses, indicador='Reclamações', formato='Linha'):
    campo, base, tipo = INDICADORES[indicador]
    serie = preparar_serie(dados, meses, campo)
    valores = [None if pd.isna(v) else float(v) for v in serie[campo]]
    # Rótulos nas extremidades; todos os valores e variações continuam no hover.
    observados = serie[campo].dropna()
    rotulados = set(observados.index) if len(observados) <= 3 else {observados.index[0], observados.index[-1]}
    textos = [formatar(v, tipo) if pd.notna(v) and m in rotulados else '' for m, v in serie[campo].items()]
    detalhes = []
    for mes, linha in serie.iterrows():
        valor = linha[campo]
        anterior = serie.loc[mes - 1, campo] if mes - 1 in serie.index else None
        variacao = 'Sem comparação com o mês anterior'
        if pd.notna(valor) and pd.notna(anterior):
            diferenca = float(valor) - float(anterior)
            if tipo in ('nota', 'percentual'):
                unidade = 'p.p.' if tipo == 'percentual' else 'pontos'
                variacao = f"{diferenca:+.2f}".replace('.', ',') + f' {unidade} ante o mês anterior'
            elif anterior != 0:
                variacao = f'{100 * diferenca / float(anterior):+.2f}% ante o mês anterior'.replace('.', ',')
        base_texto = f'Base: {numero(linha[base])} registros informados' if base and pd.notna(linha.get(base)) else ''
        detalhes.append([formatar(valor, tipo), variacao, base_texto])
    comum = dict(x=[MESES[mes] for mes in serie.index], y=valores, text=textos,
                 cliponaxis=False, customdata=detalhes,
                 hovertemplate='<b>%{x}</b><br>%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>')
    if formato == 'Colunas':
        figura = go.Figure(go.Bar(**comum, marker_color='#2563eb', textposition='outside'))
    else:
        figura = go.Figure(go.Scatter(**comum, mode='lines+markers+text', connectgaps=False,
                                     line={'color': '#2563eb', 'width': 3}, marker={'size': 11},
                                     textposition='top center', textfont={'size': 14}))
    figura.update_layout(height=440, margin={'l': 20, 'r': 55, 't': 45, 'b': 45},
                         xaxis_title='Mês de finalização', yaxis_title=indicador,
                         hovermode='x unified', showlegend=False,
                         xaxis={'type': 'category', 'categoryorder': 'array',
                                'categoryarray': [MESES[mes] for mes in serie.index]})
    figura.update_xaxes(tickmode='array', tickvals=[MESES[m] for m in serie.index],
                        ticktext=[MESES[m][:3] for m in serie.index], tickangle=0)
    figura.update_yaxes(rangemode='tozero')
    if tipo == 'nota':
        figura.update_yaxes(range=[0, 5.6])
    elif tipo == 'percentual':
        figura.update_yaxes(range=[0, 110], ticksuffix='%')
    return figura


def evolucao(dados, meses, namespace):
    with st.container(border=True):
        st.subheader('Evolução mensal')
        st.caption('Compare os meses do recorte: valores, tendência e variação em relação ao mês anterior.')
        indicador = 'Reclamações'
        formato = st.radio('Formato do volume mensal', ['Linha', 'Colunas'], horizontal=True,
                           key=f'{namespace}_monthly_format') if indicador == 'Reclamações' else 'Linha'
        campo, _, tipo = INDICADORES[indicador]
        serie = preparar_serie(dados, meses, campo)
        observados = serie[campo].dropna()
        if observados.empty:
            st.info('Não há valores informados para este indicador no recorte.')
            return
        ultimo_mes = observados.index[-1]
        pico_mes = observados.idxmax()
        anterior = serie.loc[ultimo_mes - 1, campo] if ultimo_mes - 1 in serie.index else None
        ultimo = observados.loc[ultimo_mes]
        variacao = 'N/D'
        if pd.notna(anterior):
            diferenca = float(ultimo) - float(anterior)
            if tipo in ('nota', 'percentual'):
                unidade = 'p.p.' if tipo == 'percentual' else 'pontos'
                variacao = f"{diferenca:+.2f}".replace('.', ',') + f' {unidade}'
            elif anterior != 0:
                variacao = f'{100 * diferenca / float(anterior):+.2f}%'.replace('.', ',')
        ultimo_col, variacao_col, pico_col = st.columns(3)
        ultimo_col.markdown(f'Último mês com valor · {MESES[ultimo_mes]}\n\n**{formatar(ultimo, tipo)}**')
        variacao_col.markdown(f'Variação ante o mês anterior\n\n**{variacao}**')
        pico_col.markdown(f'Maior valor · {MESES[pico_mes]}\n\n**{formatar(observados.loc[pico_mes], tipo)}**')
        st.plotly_chart(figura_mensal(dados, meses, indicador, formato), width='stretch',
                        key=f'{namespace}_monthly_chart')
        st.caption('Lacunas preservam meses fora da seleção, sem registros ou sem base para a média; a linha não conecta essas lacunas. Variação exige meses consecutivos com valores; base anterior zero produz N/D para variação percentual.')



def atendimento_mensal(dados, meses):
    evolucao(dados, meses, 'service')
    st.subheader('Qualidade do atendimento por mês')
    with st.container(key='service_quality'):
        for coluna, indicador in zip(st.columns(3), ['Tempo médio de resposta', 'Nota média', 'Respondidas (%)']):
            with coluna:
                st.markdown(f'**{indicador}**')
                campo, _, _ = INDICADORES[indicador]
                if dados[campo].notna().any():
                    figura = figura_mensal(dados, meses, indicador)
                    figura.update_layout(height=310, margin={'l': 5, 'r': 15, 't': 30, 'b': 40})
                    figura.update_traces(mode='lines+markers', text=None)
                    figura.update_xaxes(tickmode='array', tickvals=[MESES[m] for m in range(min(meses), max(meses) + 1)],
                                        ticktext=[MESES[m][:3] for m in range(min(meses), max(meses) + 1)])
                    st.plotly_chart(figura, width='stretch', key=f'service_small_{campo}')
                else:
                    st.info('Sem valores informados no recorte.')
    st.caption('Escalas independentes; bases no hover. Tempo na unidade da fonte, nota entre 1 e 5 e respostas entre 0% e 100%. Resposta não significa resolução.')


def figura_comparacao(dados, meses, empresas, participacao=False):
    figura = go.Figure()
    campo = 'participacao' if participacao else 'reclamacoes'
    for empresa, cor in zip(empresas, ['#2563eb', '#c2410c', '#0f766e']):
        selecionada = dados[dados['empresa'] == empresa]
        serie = preparar_serie(selecionada, meses, campo)
        valores = [None if pd.isna(v) else float(v) for v in serie[campo]]
        detalhes = [[numero(linha['reclamacoes']) if pd.notna(linha['reclamacoes']) else 'N/D',
                     numero(linha['total_mes']) if pd.notna(linha['total_mes']) else 'N/D',
                     formatar(linha['participacao'], 'percentual')]
                    for _, linha in serie.iterrows()]
        figura.add_trace(go.Scatter(
            x=[MESES[m] for m in serie.index], y=valores, name=empresa,
            mode='lines+markers', connectgaps=False, line={'color': cor, 'width': 3},
            marker={'size': 9}, customdata=detalhes,
            hovertemplate='%{fullData.name}<br>%{x}<br>%{customdata[0]} reclamações<br>%{customdata[2]} do mês<br>Total do mês: %{customdata[1]}<extra></extra>'))
    figura.update_layout(height=440, xaxis_title='Mês de finalização',
                         yaxis_title='Participação no total mensal (%)' if participacao else 'Reclamações',
                         hovermode='x unified', legend={'orientation': 'h', 'y': -0.25},
                         margin={'l': 20, 'r': 25, 't': 25, 'b': 90})
    figura.update_xaxes(tickmode='array', tickvals=[MESES[m] for m in range(min(meses), max(meses)+1)],
                        ticktext=[MESES[m][:3] for m in range(min(meses), max(meses)+1)], tickangle=0)
    figura.update_yaxes(rangemode='tozero', ticksuffix='%' if participacao else '')
    return figura
