"""Semântica SQL do dashboard em PostgreSQL temporário, nunca no banco da aplicação."""
import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="Requer dependências opcionais do dashboard.")
from sqlalchemy import create_engine

from dashboard.services import analytics, overview


@pytest.fixture
def dashboard_database(postgres, monkeypatch):
    sql, load = postgres
    sql('TRUNCATE metadata.gold_load_control, staging.complaints, warehouse.fato_reclamacao, '
        'warehouse.dim_empresa, warehouse.dim_localidade, warehouse.dim_tempo, '
        'warehouse.dim_classificacao RESTART IDENTITY')
    sql("""
        INSERT INTO staging.complaints
            (data_finalizacao, nome_fantasia, segmento_de_mercado, uf, cidade,
             tempo_resposta, nota_do_consumidor, avaliacao_reclamacao, area)
        VALUES
            ('2026-07-01', ' Empresa ', 'A', 'SP', 'São Paulo', 10, 1, 'Resolvida', ' Financeiro '),
            ('2026-07-02', 'Empresa', 'B', 'RJ', 'Rio de Janeiro', NULL, NULL, 'Não Avaliada', 'Financeiro'),
            ('2026-07-03', 'Outra', 'A', 'DF', 'Brasília', 20, 5, 'Resolvida', NULL),
            ('2026-07-04', 'Outra', 'A', 'SP', 'São Paulo', NULL, 4, NULL, 'Não informado');
    """)
    result = load('2026-07')
    assert result.returncode == 0, result.stderr
    sql("""
        TRUNCATE staging.complaints;
        INSERT INTO staging.complaints
            (data_finalizacao, nome_fantasia, segmento_de_mercado, uf, cidade,
             tempo_resposta, avaliacao_reclamacao)
        VALUES ('2026-08-01', 'Empresa', 'A', 'SP', 'São Paulo', 30, 'Não Avaliada');
    """)
    result = load('2026-08')
    assert result.returncode == 0, result.stderr
    monkeypatch.setattr(analytics, 'get_engine', lambda: create_engine(sql.connection_url))
    monkeypatch.setattr(analytics, 'BANCO_ESPERADO', sql.connection_url.database)
    analytics.consultar_lote.clear()
    yield sql
    analytics.consultar_lote.clear()


def test_company_count_and_ranking_share_name_definition(dashboard_database):
    data = overview.carregar_visao_geral(2026, [7])
    kpis = data['indicadores'].iloc[0]
    assert kpis['reclamacoes'] == 4
    assert kpis['empresas'] == 2  # Há três IDs de empresa, mas dois nomes fantasia.
    assert kpis['ufs'] == 3  # DF também é UF.
    assert data['empresas'].set_index('empresa')['reclamacoes'].to_dict() == {'Empresa': 2, 'Outra': 2}
    assert data['areas'].set_index('area')['reclamacoes'].to_dict() == {'Financeiro': 2, 'Não informado': 2}


def test_means_exclude_nulls_and_report_denominators(dashboard_database):
    kpis = overview.carregar_visao_geral(2026, [7])['indicadores'].iloc[0]
    assert kpis['tempo_medio'] == 15
    assert kpis['base_tempo'] == 2
    assert kpis['nota_media'] == pytest.approx(3.33)
    assert kpis['base_nota'] == 3  # Inclui nota preenchida com rótulo de avaliação ausente.


def test_every_chart_uses_exactly_selected_months(dashboard_database):
    selected = overview.carregar_visao_geral(2026, [8])
    assert selected['mensal']['mes'].tolist() == [8]
    assert selected['indicadores'].iloc[0]['reclamacoes'] == 1
    for chart in ('mensal', 'empresas', 'estados', 'areas'):
        assert selected[chart]['reclamacoes'].sum() == 1
    combined = overview.carregar_visao_geral(2026, [8, 7])
    assert combined['mensal']['mes'].tolist() == [7, 8]
    assert combined['indicadores'].iloc[0]['reclamacoes'] == 5
    for chart in ('mensal', 'empresas', 'estados', 'areas'):
        assert combined[chart]['reclamacoes'].sum() == 5


def test_missing_scores_and_missing_period_are_not_zero_means(dashboard_database):
    kpis = overview.carregar_visao_geral(2026, [8])['indicadores'].iloc[0]
    assert pd.isna(kpis['nota_media'])
    assert kpis['base_nota'] == 0
    empty = overview.carregar_visao_geral(2026, [9])
    assert empty['indicadores'].iloc[0]['reclamacoes'] == 0
    assert pd.isna(empty['indicadores'].iloc[0]['tempo_medio'])
    assert pd.isna(empty['indicadores'].iloc[0]['nota_media'])
    assert empty['mensal'].empty  # Não fabrica uma barra de zero para mês sem carga.


def test_readonly_transaction_uses_same_snapshot_for_entire_batch(dashboard_database):
    query = """SELECT current_setting('transaction_read_only') AS readonly,
                      current_setting('transaction_isolation') AS isolation,
                      txid_current_snapshot()::text AS snapshot"""
    result = analytics.consultar_lote({'first': query, 'second': query})
    first, second = result['first'].iloc[0], result['second'].iloc[0]
    assert first['readonly'] == 'on'
    assert first['isolation'] == 'repeatable read'
    assert first['snapshot'] == second['snapshot']


def test_readonly_transaction_blocks_writing_cte(dashboard_database):
    before = dashboard_database('SELECT COUNT(*) FROM warehouse.fato_reclamacao')
    with pytest.raises(pd.errors.DatabaseError) as error:
        analytics.consultar("""
            WITH changed AS (DELETE FROM warehouse.fato_reclamacao RETURNING reclamacao_id)
            SELECT COUNT(*) FROM changed
        """)
    assert error.value.__cause__.orig.sqlstate == '25006'  # ReadOnlySqlTransaction
    assert dashboard_database('SELECT COUNT(*) FROM warehouse.fato_reclamacao') == before


def test_benchmark_collects_real_plans_in_readonly_snapshot(dashboard_database):
    from scripts.benchmark_dashboard import benchmark
    engine = create_engine(dashboard_database.connection_url)
    before = dashboard_database('SELECT COUNT(*) FROM warehouse.fato_reclamacao')
    try:
        with engine.connect() as connection:
            report = benchmark(connection, 2026, {'selecionado': [7]}, repetitions=1, warmup=0, compare_reference=True)
    finally:
        engine.dispose()
    assert report['server']['read_only'] == 'on'
    assert report['scenarios']['selecionado']['kpi_comparison']['results_equal'] is True
    assert set(report['scenarios']['selecionado']['queries']) == {'indicadores', 'mensal', 'empresas', 'estados', 'areas'}
    for result in report['scenarios']['selecionado']['queries'].values():
        assert result['samples'][0]['plan']['Execution Time'] >= 0
        assert result['median_execution_ms'] >= 0
    assert dashboard_database('SELECT COUNT(*) FROM warehouse.fato_reclamacao') == before


def test_optimized_kpis_match_reference_with_unequal_groups(dashboard_database):
    from pathlib import Path
    from sqlalchemy import text
    # Três linhas adicionais no mesmo grupo: impede uma média de médias sem peso.
    dashboard_database("""
        INSERT INTO warehouse.fato_reclamacao
            (empresa_id, localidade_id, data_id, classificacao_id,
             tempo_resposta, nota_do_consumidor, avaliacao_reclamacao)
        SELECT empresa_id, localidade_id, data_id, classificacao_id, 2, 5, 'Resolvida'
        FROM warehouse.fato_reclamacao
        CROSS JOIN generate_series(1, 3)
        WHERE data_id=20260701;
    """)
    reference = (Path(__file__).resolve().parents[1] / 'sql/analytics/dashboard_kpis_reference.sql').read_text()
    engine = create_engine(dashboard_database.connection_url)
    try:
        with engine.connect() as connection:
            for months in ([7], [8], [7, 8], [9]):
                parameters = {'ano': 2026, 'meses': months}
                original = dict(connection.execute(text(reference), parameters).mappings().one())
                current = dict(connection.execute(text(overview.CONSULTAS['indicadores']), parameters).mappings().one())
                assert original == current
                if months == [7]:
                    assert current['reclamacoes'] == 7
                    assert float(current['tempo_medio']) == 7.2
                    assert current['base_tempo'] == 5
                    assert float(current['nota_media']) == 4.17
                    assert current['base_nota'] == 6
    finally:
        engine.dispose()
