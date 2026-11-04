"""Contratos visuais: correspondência territorial e leitura exata das figuras."""
import pandas as pd
import pytest

pytest.importorskip('plotly')

from dashboard.components.charts import CODIGOS_UF, distribuicao_notas, malha_ufs, mapa_ufs, ranking


def test_local_geometry_contains_all_27_ufs_including_df():
    features = malha_ufs()['features']
    codes = [feature['properties']['codarea'] for feature in features]
    assert len(features) == len(set(codes)) == 27
    assert set(codes) == set(CODIGOS_UF.values())
    assert CODIGOS_UF['DF'] == '53'
    assert all(feature['geometry']['type'] in ('Polygon', 'MultiPolygon') for feature in features)


def test_map_links_counts_to_correct_geometry_and_keeps_absence_separate():
    counts = pd.DataFrame({'uf': ['SP', 'DF'], 'reclamacoes': [1200, 300]})
    figure = mapa_ufs(counts)
    background, values = figure.data
    assert values.type == 'choroplethmap'
    assert all(trace.type != 'scattermap' for trace in figure.data)
    assert list(values.locations) == [CODIGOS_UF['SP'], CODIGOS_UF['DF']]
    assert list(values.z) == [1200, 300]
    assert values.showscale is True
    assert values.zmin == 0
    assert values.zmax == 1200
    assert list(values.customdata[0]) == ['SP', '1.200', '80,00%']
    assert list(values.customdata[1]) == ['DF', '300', '20,00%']
    assert len(background.locations) == 27
    assert 'Sem registros' in background.customdata[0][1]
    assert figure.layout.map.style == 'white-bg'  # Sem provedor externo de tiles.
    assert figure.layout.map.fitbounds is False
    assert figure.layout.map.center.lat == -14.5
    assert figure.layout.map.center.lon == -53.2
    assert figure.layout.map.zoom == 3.2
    assert background.featureidkey == 'properties.codarea'
    assert values.featureidkey == 'properties.codarea'
    assert values.colorscale[0][1] != values.colorscale[-1][1]


def test_filtered_map_marks_other_ufs_as_outside_filter():
    figure = mapa_ufs(pd.DataFrame({'uf': ['DF'], 'reclamacoes': [2]}), 'DF')
    assert figure.data[0].customdata[0][1] == 'Fora do filtro de UF'
    assert figure.data[1].customdata[0][2] == '100,00%'
    assert figure.data[1].customdata[0][0] == 'DF'


def test_empty_map_does_not_fabricate_observed_zeros():
    figure = mapa_ufs(pd.DataFrame(columns=['uf', 'reclamacoes']))
    assert len(figure.data) == 1
    assert figure.data[0].showscale is False


def test_rankings_preserve_exact_counts_order_and_full_hover_labels():
    long_name = 'Problema com uma descrição muito longa que deve continuar disponível integralmente no hover'
    frame = pd.DataFrame({'categoria': [long_name, 'B', 'A'], 'reclamacoes': [1200, 5, 5]})
    figure = ranking(frame, 'categoria', 'Categoria')
    assert figure.data[0].orientation == 'h'
    assert list(figure.data[0].y) == ['B', 'A', long_name]
    assert list(figure.data[0].text) == ['5', '5', '1.200']
    assert len(figure.layout.yaxis.ticktext[-1]) <= 65
    assert figure.data[0].cliponaxis is False


def test_score_distribution_uses_fixed_order_and_excludes_missing_scores():
    figure = distribuicao_notas(pd.DataFrame({'nota': [1, 5], 'reclamacoes': [4, 2]}))
    assert list(figure.data[0].x) == [1, 2, 3, 4, 5]
    assert list(figure.data[0].y) == [4, 0, 0, 0, 2]
    assert sum(figure.data[0].y) == 6


def test_map_positions_are_derived_from_each_uf_geometry():
    from dashboard.components.charts import centros_ufs
    centers = centros_ufs()
    assert set(centers) == set(CODIGOS_UF.values())
    lon, lat = centers['53']
    assert -49 < lon < -47
    assert -17 < lat < -15
    assert all(-75 < lon < -32 and -35 < lat < 6 for lon, lat in centers.values())
