"""Figuras reutilizáveis: mapa local, rankings legíveis e notas discretas."""

import json
from functools import lru_cache
from pathlib import Path
from textwrap import shorten

import plotly.graph_objects as go

from dashboard.components.formatting import inteiro as numero
from dashboard.constants import ESTADOS


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


def mapa_ufs(estados, uf_selecionada=None, rotulos='Siglas'):
    """Preenchimento das UFs por volume; ausência e fora do filtro ficam em cinza."""
    if rotulos not in ('Siglas', 'Nomes completos', 'Sem rótulos'):
        raise ValueError('Identificação de estados inválida.')
    malha = malha_ufs()
    ufs = list(CODIGOS_UF)
    contagens = dict(zip(estados['uf'], estados['reclamacoes']))
    figura = go.Figure(go.Choroplethmap(
        geojson=malha, featureidkey='properties.codarea',
        locations=[CODIGOS_UF[uf] for uf in ufs], z=[0] * len(ufs),
        colorscale=[[0, '#e2e8f0'], [1, '#e2e8f0']], showscale=False,
        marker_line_color='#ffffff', marker_line_width=1,
        customdata=[[uf, 'Fora do filtro de UF' if uf_selecionada and uf != uf_selecionada else f'{numero(contagens[uf])} reclamações no recorte' if uf in contagens else 'Sem registros no recorte', ESTADOS[uf]] for uf in ufs],
        hovertemplate='<b>%{customdata[2]} (%{customdata[0]})</b><br>%{customdata[1]}<extra></extra>',
    ))
    total = int(estados['reclamacoes'].sum())
    if not estados.empty:
        figura.add_trace(go.Choroplethmap(
            geojson=malha, featureidkey='properties.codarea',
            locations=[CODIGOS_UF[uf] for uf in estados['uf']],
            z=estados['reclamacoes'].astype(int).tolist(),
            zmin=0, zmax=max(int(estados['reclamacoes'].max()), 1),
            colorscale=[[0, '#dbeafe'], [0.5, '#3b82f6'], [1, '#1e3a8a']],
            showscale=True, colorbar={'title': 'Reclamações', 'thickness': 12, 'orientation': 'h', 'x': 0.5, 'y': -0.04, 'len': 0.9},
            marker_line_color='#ffffff', marker_line_width=1,
            customdata=[[uf, numero(valor), f'{100 * valor / total:.2f}%'.replace('.', ',') if total else 'N/D', ESTADOS[uf]]
                        for uf, valor in zip(estados['uf'], estados['reclamacoes'])],
            hovertemplate='<b>%{customdata[3]} (%{customdata[0]})</b><br>%{customdata[1]} reclamações<br>%{customdata[2]} do recorte<extra></extra>',
        ))
    if rotulos != 'Sem rótulos':
        centros = centros_ufs()
        maximo = max(contagens.values(), default=1)
        for claro in (False, True):
            grupo = [uf for uf in ufs if (contagens.get(uf, 0) / max(maximo, 1) > .55) == claro]
            if not grupo:
                continue
            figura.add_trace(go.Scattermap(
                lon=[centros[CODIGOS_UF[uf]][0] for uf in grupo],
                lat=[centros[CODIGOS_UF[uf]][1] for uf in grupo],
                text=[ESTADOS[uf] if rotulos == 'Nomes completos' else uf for uf in grupo],
                mode='text', textfont={'size': 11 if rotulos == 'Nomes completos' else 12,
                                      'color': '#ffffff' if claro else '#0f172a'},
                hoverinfo='skip', showlegend=False,
            ))
    figura.update_layout(map={'style': 'white-bg', 'fitbounds': 'locations',
                             'center': {'lat': -14.5, 'lon': -53.2}, 'zoom': 2.5},
                         height=560, margin={'l': 0, 'r': 0, 't': 5, 'b': 35}, dragmode='pan', showlegend=False)
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
                         xaxis_title='Reclamações', yaxis_title=None,
                         margin={'l': 0, 'r': 75, 't': 15, 'b': 40}, showlegend=False)
    figura.update_yaxes(type='category', automargin=True, tickmode='array',
                        tickvals=ordenados[categoria].tolist(),
                        ticktext=[shorten(str(valor), width=38, placeholder='…') for valor in ordenados[categoria]])
    figura.update_xaxes(rangemode='tozero')
    return figura


def distribuicao_notas(notas):
    """Escala ordinal completa 1–5; categorias sem ocorrência têm contagem zero."""
    if not notas['nota'].isin([1, 2, 3, 4, 5]).all():
        raise ValueError('Distribuição exige notas inteiras de 1 a 5.')
    contagens = notas.groupby('nota')['reclamacoes'].sum().reindex([1, 2, 3, 4, 5], fill_value=0)
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
