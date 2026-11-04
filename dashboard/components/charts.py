"""Figuras reutilizáveis: mapa local, rankings legíveis e notas discretas."""

import json
from functools import lru_cache
from pathlib import Path
from textwrap import shorten

import plotly.graph_objects as go

from dashboard.components.formatting import inteiro as numero


CODIGOS_UF = dict(zip(
    'RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF'.split(),
    '11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53'.split(),
))


@lru_cache(maxsize=1)
def malha_ufs():
    arquivo = Path(__file__).resolve().parents[1] / 'assets' / 'br_ufs.geojson'
    return json.loads(arquivo.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def centros_ufs():
    """Posições representativas: centroides do maior polígono de cada UF."""
    centros = {}
    for feicao in malha_ufs()['features']:
        geometria = feicao['geometry']
        aneis = [geometria['coordinates'][0]] if geometria['type'] == 'Polygon' else [p[0] for p in geometria['coordinates']]
        candidatos = []
        for anel in aneis:
            cruzados = [a[0] * b[1] - b[0] * a[1] for a, b in zip(anel, anel[1:])]
            area_dupla = sum(cruzados)
            if area_dupla:
                lon = sum((a[0] + b[0]) * c for a, b, c in zip(anel, anel[1:], cruzados)) / (3 * area_dupla)
                lat = sum((a[1] + b[1]) * c for a, b, c in zip(anel, anel[1:], cruzados)) / (3 * area_dupla)
                candidatos.append((abs(area_dupla), lon, lat))
        _, lon, lat = max(candidatos)
        centros[feicao['properties']['codarea']] = (lon, lat)
    return centros


def mapa_ufs(estados, uf_selecionada=None):
    """Preenchimento das UFs por volume; ausência e fora do filtro ficam em cinza."""
    malha = malha_ufs()
    ufs = list(CODIGOS_UF)
    contagens = dict(zip(estados['uf'], estados['reclamacoes']))
    figura = go.Figure(go.Choroplethmap(
        geojson=malha, featureidkey='properties.codarea',
        locations=[CODIGOS_UF[uf] for uf in ufs], z=[0] * len(ufs),
        colorscale=[[0, '#e2e8f0'], [1, '#e2e8f0']], showscale=False,
        marker_line_color='#ffffff', marker_line_width=1,
        customdata=[[uf, 'Fora do filtro de UF' if uf_selecionada and uf != uf_selecionada else f'{numero(contagens[uf])} reclamações no recorte' if uf in contagens else 'Sem registros no recorte'] for uf in ufs],
        hovertemplate='<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>',
    ))
    total = int(estados['reclamacoes'].sum())
    if not estados.empty:
        figura.add_trace(go.Choroplethmap(
            geojson=malha, featureidkey='properties.codarea',
            locations=[CODIGOS_UF[uf] for uf in estados['uf']],
            z=estados['reclamacoes'].astype(int).tolist(),
            zmin=0, zmax=max(int(estados['reclamacoes'].max()), 1),
            colorscale=[[0, '#dbeafe'], [0.5, '#3b82f6'], [1, '#1e3a8a']],
            showscale=True, colorbar={'title': 'Reclamações', 'thickness': 16},
            marker_line_color='#ffffff', marker_line_width=1,
            customdata=[[uf, numero(valor), f'{100 * valor / total:.2f}%'.replace('.', ',') if total else 'N/D']
                        for uf, valor in zip(estados['uf'], estados['reclamacoes'])],
            hovertemplate='<b>%{customdata[0]}</b><br>%{customdata[1]} reclamações<br>%{customdata[2]} do recorte<extra></extra>',
        ))
    figura.update_layout(map={'style': 'white-bg', 'fitbounds': False,
                             'center': {'lat': -14.5, 'lon': -53.2}, 'zoom': 3.2},
                         height=620, margin={'l': 0, 'r': 0, 't': 5, 'b': 0}, dragmode='pan', showlegend=False)
    return figura


def ranking(dados, categoria, rotulo):
    ordenados = dados.sort_values(['reclamacoes', categoria], ascending=[True, False])
    figura = go.Figure(go.Bar(
        x=ordenados['reclamacoes'].tolist(), y=ordenados[categoria].tolist(), orientation='h',
        text=[numero(valor) for valor in ordenados['reclamacoes']], textposition='outside',
        cliponaxis=False, marker_color='#2563eb',
        hovertemplate='%{y}<br>%{text} reclamações<extra></extra>',
    ))
    figura.update_layout(height=max(300, 32 * len(ordenados) + 100),
                         xaxis_title='Reclamações', yaxis_title=rotulo,
                         margin={'l': 0, 'r': 75, 't': 15, 'b': 40}, showlegend=False)
    figura.update_yaxes(type='category', automargin=True, tickmode='array',
                        tickvals=ordenados[categoria].tolist(),
                        ticktext=[shorten(str(valor), width=65, placeholder='…') for valor in ordenados[categoria]])
    figura.update_xaxes(rangemode='tozero')
    return figura


def distribuicao_notas(notas):
    """Escala ordinal completa 1–5; categorias sem ocorrência têm contagem zero."""
    contagens = notas.set_index('nota')['reclamacoes'].reindex([1, 2, 3, 4, 5], fill_value=0)
    figura = go.Figure(go.Bar(
        x=[1, 2, 3, 4, 5], y=contagens.astype(int).tolist(),
        text=[numero(valor) for valor in contagens], textposition='outside',
        cliponaxis=False, marker_color='#2563eb',
        hovertemplate='Nota %{x}<br>%{text} reclamações<extra></extra>',
    ))
    figura.update_layout(xaxis_title='Nota do consumidor', yaxis_title='Reclamações',
                         height=340, margin={'l': 0, 'r': 25, 't': 25, 'b': 40})
    figura.update_xaxes(tickmode='array', tickvals=[1, 2, 3, 4, 5])
    figura.update_yaxes(rangemode='tozero')
    return figura
