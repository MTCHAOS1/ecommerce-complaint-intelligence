"""Apresentação com textos completos e indicador de processamento analítico."""

from html import escape
from urllib.parse import quote

import streamlit as st

from dashboard.components.charts import numero


LOADING_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" fill="none">
<path d="M4 5v21h21" stroke="#64748b" stroke-width="2" stroke-linecap="round"/>
<path d="M9 22v-7m6 7V10m6 12V6" stroke="#2563eb" stroke-width="3" stroke-linecap="round"/>
<circle cx="22" cy="20" r="6" fill="#dbeafe" stroke="#0f766e" stroke-width="2"/>
<path d="m26.5 24.5 4 4" stroke="#0f766e" stroke-width="3" stroke-linecap="round"/>
</svg>'''


def estilos_loading():
    """Seleciona só o ícone de execução; mantém Stop e o estado nativo."""
    imagem = 'data:image/svg+xml,' + quote(LOADING_SVG, safe='')
    return f'''<style>
    [data-testid="stStatusWidgetRunningIcon"] {{
        width: 2rem; height: 2rem; flex-shrink: 0;
    }}
    [data-testid="stStatusWidgetRunningIcon"] > svg,
    [data-testid="stStatusWidgetRunningIcon"] > img {{ display: none; }}
    [data-testid="stStatusWidgetRunningIcon"]::before {{
        content: ""; display: block; width: 2rem; height: 2rem;
        background: center / contain no-repeat url("{imagem}");
        animation: eci-analyzing 1.2s ease-in-out infinite;
    }}
    @keyframes eci-analyzing {{
        0%, 100% {{ opacity: 0.65; transform: translateY(0); }}
        50% {{ opacity: 1; transform: translateY(-2px); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
        [data-testid="stStatusWidgetRunningIcon"]::before {{ animation: none; }}
    }}
    </style>'''


def aplicar_identidade():
    st.html(estilos_loading() + """<style>
    [data-testid="stMain"] { container-type: inline-size; }
    [data-testid="stMainBlockContainer"] { padding-top: 2rem; }
    [data-testid="stMain"] h1 { font-size: clamp(1.5rem, 2.6vw, 2rem); line-height: 1.25; }
    [data-testid="stMetricLabel"] p { white-space: normal; overflow: visible; }
    @container (max-width: 850px) {
      .st-key-overview_rankings [data-testid="stHorizontalBlock"],
      .st-key-service_quality [data-testid="stHorizontalBlock"] { flex-direction: column; }
      .st-key-overview_rankings [data-testid="stColumn"],
      .st-key-service_quality [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100%; }
    }
    </style>""")


def ranking_completo_html(dados, categoria, titulo):
    """Rótulos fora do eixo, sem abreviação, com wrapping até de palavras longas."""
    ordenados = dados.sort_values(['reclamacoes', categoria], ascending=[False, True])
    maximo = float(ordenados['reclamacoes'].max()) if not ordenados.empty else 0
    linhas = []
    for _, linha in ordenados.iterrows():
        valor = int(linha['reclamacoes'])
        largura = 100 * valor / maximo if maximo else 0
        linhas.append(f'''<li class="eci-ranking-item">
            <div class="eci-ranking-heading">
                <span class="eci-ranking-label">{escape(str(linha[categoria]))}</span>
                <strong class="eci-ranking-value">{numero(valor)}<span> reclamações</span></strong>
            </div>
            <div class="eci-ranking-track" aria-hidden="true">
                <div class="eci-ranking-fill" style="width:{largura:.4f}%"></div>
            </div>
        </li>''')
    return '''<style>
    .eci-full-ranking { width: 100%; min-width: 0; }
    .eci-full-ranking ol { margin: 0; padding: 0; list-style: none; }
    .eci-full-ranking .eci-ranking-item { margin: 0 0 1.25rem; padding: 0; }
    .eci-ranking-heading { display: flex; flex-wrap: wrap; align-items: baseline;
        justify-content: space-between; gap: .25rem 1rem; margin-bottom: .5rem; }
    .eci-full-ranking .eci-ranking-label { flex: 1 1 22rem; min-width: 0;
        white-space: normal; overflow-wrap: anywhere; word-break: normal;
        line-height: 1.5; font-size: 1rem; }
    .eci-ranking-value { flex: 0 0 auto; font-variant-numeric: tabular-nums; }
    .eci-ranking-value span { font-size: .85rem; font-weight: normal; }
    .eci-ranking-track { height: .7rem; width: 100%; border-radius: .25rem;
        background: rgba(100, 116, 139, .18); }
    .eci-ranking-fill { height: 100%; border-radius: .25rem; background: #2563eb; }
    </style><section class="eci-full-ranking" aria-label="''' + escape(titulo, quote=True) + '"><ol>' + ''.join(linhas) + '</ol></section>'


def ranking_completo(dados, categoria, titulo):
    st.subheader(titulo)
    if dados.empty:
        st.info('Não há categorias para o recorte selecionado.')
        return
    st.html(ranking_completo_html(dados, categoria, titulo))


def tabela_problemas_html(dados):
    """Top 10 com barras comparáveis, textos completos e rolagem por teclado."""
    ordenados = dados.sort_values(
        ['reclamacoes', 'problema'], ascending=[False, True],
    ).head(10)
    maximo = float(ordenados['reclamacoes'].max()) if not ordenados.empty else 0
    linhas = []
    for _, linha in ordenados.iterrows():
        valor = int(linha['reclamacoes'])
        largura = 100 * valor / maximo if maximo else 0
        linhas.append(
            '<tr>'
            '<td class="eci-problem-text">'
            f'<div>{escape(str(linha["problema"]))}</div>'
            '<div class="eci-problem-track" aria-hidden="true">'
            f'<div class="eci-problem-bar" style="width:{largura:.4f}%"></div>'
            '</div></td>'
            f'<td class="eci-problem-count">{numero(valor)}</td>'
            '</tr>'
        )
    return '''<style>
    .eci-problems-scroll { max-height: 520px; overflow: auto; width: 100%;
        border: 1px solid rgba(100, 116, 139, .35); border-radius: .5rem; }
    .eci-problems-scroll:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
    .eci-problems-table { width: 100%; min-width: 0; table-layout: fixed; border-collapse: separate;
        border-spacing: 0; font-size: 1rem; line-height: 1.6; }
    .eci-problems-table th { position: sticky; top: 0; background: #1e293b; color: #f8fafc;
        z-index: 1; text-align: left; font-weight: 600; }
    .eci-problems-table th, .eci-problems-table td { padding: .85rem 1rem;
        border-bottom: 1px solid rgba(100, 116, 139, .25); vertical-align: top; }
    .eci-problems-table tbody tr:nth-child(even) { background: rgba(100, 116, 139, .06); }
    .eci-problems-table .eci-problem-text { white-space: normal; overflow-wrap: anywhere; }
    .eci-problem-track { width: 100%; height: .8rem; margin-top: .65rem;
        border-radius: .25rem; background: rgba(100, 116, 139, .15); }
    .eci-problem-bar { height: 100%; border-radius: .25rem; background: #2563eb; }
    .eci-problems-table .eci-problem-count { text-align: right; white-space: nowrap;
        font-variant-numeric: tabular-nums; font-weight: 600; width: 8rem; }
    .eci-problems-table th.eci-problem-count { white-space: normal; }
    </style><div class="eci-problems-scroll" role="region" tabindex="0"
        aria-label="Principais problemas, até 10, barras e tabela com rolagem">
    <table class="eci-problems-table"><thead><tr>
        <th scope="col">Classificação do problema</th>
        <th scope="col" class="eci-problem-count">Quantidade de reclamações</th>
    </tr></thead><tbody>''' + ''.join(linhas) + '</tbody></table></div>'


def tabela_problemas(dados):
    st.subheader('Principais problemas — até 10')
    if dados.empty:
        st.info('Não há problemas para o recorte selecionado.')
        return
    st.caption('Até 10 problemas com mais reclamações no recorte. Valores à direita; barras na mesma escala. Role o painel para ver todos os itens.')
    st.html(tabela_problemas_html(dados))
