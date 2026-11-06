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


def test_company_detail_groups_segments_and_filters_months(dashboard_database):
    from dashboard.services.companies import carregar_empresa, listar_empresas
    assert listar_empresas(2026, [7])['empresa'].tolist() == ['Empresa', 'Outra']
    result = carregar_empresa(2026, [7], ' Empresa ')
    kpis = result['indicadores'].iloc[0]
    assert kpis['reclamacoes'] == 2
    assert kpis['tempo_medio'] == 10
    assert kpis['base_tempo'] == 1
    assert kpis['nota_media'] == 1
    assert kpis['base_nota'] == 1
    assert result['mensal']['mes'].tolist() == [7]
    assert result['problemas'].iloc[0]['problema'] == 'Não informado'
    assert result['problemas']['reclamacoes'].sum() == 2
    assert carregar_empresa(2026, [8], 'Empresa')['indicadores'].iloc[0]['reclamacoes'] == 1
    assert carregar_empresa(2026, [7], "Empresa' OR TRUE --")['indicadores'].iloc[0]['reclamacoes'] == 0


def test_company_problems_returns_only_ten_largest_categories(dashboard_database):
    from dashboard.services.companies import carregar_empresa
    dashboard_database("""
        TRUNCATE staging.complaints;
        INSERT INTO staging.complaints
            (data_finalizacao, nome_fantasia, uf, cidade, problema)
        SELECT '2026-07-01'::date, 'Empresa', 'SP', 'São Paulo',
               'Problema ' || LPAD(category::text, 2, '0')
        FROM generate_series(1, 12) AS category
        CROSS JOIN LATERAL generate_series(1, category) AS occurrence;
    """)
    result = dashboard_database.load('2026-07')
    assert result.returncode == 0, result.stderr
    data = carregar_empresa(2026, [7], 'Empresa')
    assert data['problemas']['problema'].tolist() == [
        f'Problema {category:02d}' for category in range(12, 2, -1)
    ]
    assert data['problemas']['reclamacoes'].tolist() == list(range(12, 2, -1))
    assert data['indicadores'].iloc[0]['reclamacoes'] == sum(range(1, 13))


def test_dashboard_reader_has_select_without_write_privileges(dashboard_database):
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / 'sql/analytics/create_dashboard_reader.sql').read_text()
    dashboard_database(script)
    try:
        result = dashboard_database("""
            SELECT has_table_privilege('complaints_dashboard', 'warehouse.fato_reclamacao', 'SELECT'),
                   has_table_privilege('complaints_dashboard', 'warehouse.fato_reclamacao', 'INSERT'),
                   has_table_privilege('complaints_dashboard', 'warehouse.fato_reclamacao', 'UPDATE'),
                   has_table_privilege('complaints_dashboard', 'warehouse.fato_reclamacao', 'DELETE'),
                   has_schema_privilege('complaints_dashboard', 'warehouse', 'CREATE');
        """)
        assert result.strip() == 't|f|f|f|f'
    finally:
        dashboard_database('DROP OWNED BY complaints_dashboard; DROP ROLE complaints_dashboard;')


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


def test_geography_filters_uf_and_distinguishes_cities(dashboard_database):
    from dashboard.services.specialized import carregar_geografia
    data = carregar_geografia(2026, [7])
    assert data['indicadores'].iloc[0].to_dict() == {'reclamacoes': 4, 'ufs': 3, 'cidades': 3}
    assert data['estados'].set_index('uf')['reclamacoes'].to_dict() == {'SP': 2, 'DF': 1, 'RJ': 1}
    assert 'Brasília / DF' in data['cidades']['cidade'].tolist()
    selected = carregar_geografia(2026, [8], 'SP')
    assert selected['mensal']['mes'].tolist() == [8]
    assert selected['indicadores'].iloc[0]['reclamacoes'] == 1
    assert carregar_geografia(2026, [7], 'AC')['cidades'].empty
    dashboard_database("UPDATE warehouse.dim_localidade SET cidade='São Paulo' WHERE uf='RJ'")
    assert carregar_geografia(2026, [7, 8])['indicadores'].iloc[0]['cidades'] == 3


def test_problem_area_filter_and_missing_categories(dashboard_database):
    from dashboard.services.specialized import carregar_problemas, listar_areas
    assert listar_areas(2026, [7])['area'].tolist() == ['Financeiro', 'Não informado']
    data = carregar_problemas(2026, [7], ' Financeiro ')
    assert data['indicadores'].iloc[0]['reclamacoes'] == 2
    for name in ('areas', 'assuntos', 'grupos', 'problemas'):
        assert data[name]['reclamacoes'].sum() == 2
    assert data['assuntos'].iloc[0]['assuntos'] == 'Não informado'
    assert carregar_problemas(2026, [7], 'Não informado')['indicadores'].iloc[0]['reclamacoes'] == 2
    assert carregar_problemas(2026, [8], 'Financeiro')['indicadores'].iloc[0]['reclamacoes'] == 0
    assert carregar_problemas(2026, [7], "' OR TRUE --")['indicadores'].iloc[0]['reclamacoes'] == 0


def test_service_response_denominator_excludes_unknown(dashboard_database):
    from dashboard.services.specialized import carregar_atendimento
    dashboard_database("UPDATE warehouse.fato_reclamacao SET respondida=CASE data_id WHEN 20260701 THEN TRUE WHEN 20260702 THEN FALSE ELSE NULL END")
    data = carregar_atendimento(2026, [7])
    kpis = data['indicadores'].iloc[0]
    assert kpis['reclamacoes'] == 4
    assert kpis['respondidas'] == 1
    assert kpis['base_respondida'] == 2
    assert kpis['percentual_respondidas'] == 50
    assert kpis['base_nota'] == 3
    assert kpis['nota_media'] == pytest.approx(3.33)
    assert data['notas']['reclamacoes'].sum() == 3
    assert data['avaliacoes']['reclamacoes'].sum() == 4
    assert data['mensal']['mes'].tolist() == [7]
    assert data['mensal'].iloc[0]['base_respondida'] == 2
    unknown = carregar_atendimento(2026, [8])['indicadores'].iloc[0]
    assert pd.isna(unknown['percentual_respondidas'])
    assert unknown['base_respondida'] == 0
    empty = carregar_atendimento(2026, [9])
    assert empty['indicadores'].iloc[0]['reclamacoes'] == 0
    assert empty['mensal'].empty


def test_problem_ranking_is_limited_and_deterministic(dashboard_database):
    from dashboard.services.specialized import carregar_problemas
    dashboard_database("""
        INSERT INTO warehouse.dim_classificacao (area, assunto, problema)
        SELECT 'Teste', 'Assunto', 'Problema ' || lpad(i::text, 2, '0') FROM generate_series(1, 20) i;
        INSERT INTO warehouse.fato_reclamacao (empresa_id, localidade_id, data_id, classificacao_id)
        SELECT f.empresa_id, f.localidade_id, f.data_id, c.classificacao_id
        FROM warehouse.fato_reclamacao f CROSS JOIN warehouse.dim_classificacao c
        WHERE f.data_id=20260701 AND c.area='Teste';
    """)
    data = carregar_problemas(2026, [7], 'Teste')
    assert data['indicadores'].iloc[0]['reclamacoes'] == 20
    assert data['problemas']['problemas'].tolist() == [f'Problema {i:02}' for i in range(1, 16)]


def test_company_comparison_uses_all_companies_in_monthly_denominator(dashboard_database):
    from dashboard.services.companies import comparar_empresas
    data = comparar_empresas(2026, [7, 8], [' Empresa ', 'Outra'])
    july = data[data.mes == 7].set_index('empresa')
    assert july['reclamacoes'].to_dict() == {'Empresa': 2, 'Outra': 2}
    assert july['participacao'].to_dict() == {'Empresa': 50, 'Outra': 50}
    alone = comparar_empresas(2026, [7], ['Empresa']).iloc[0]
    assert alone['total_mes'] == 4
    assert alone['participacao'] == 50  # Denominador não é só a seleção.
    august = data[data.mes == 8].iloc[0]
    assert august['empresa'] == 'Empresa'
    assert august['participacao'] == 100
    assert comparar_empresas(2026, [7], ["' OR TRUE --"]).empty


def test_problem_drilldown_filters_subject_and_group(dashboard_database):
    from dashboard.services.specialized import carregar_problemas, listar_assuntos, listar_grupos
    dashboard_database("""
        UPDATE warehouse.dim_classificacao
        SET assunto=' Cobrança ', grupo_problema=' Valores ', problema='Cobrança indevida'
        WHERE BTRIM(area)='Financeiro';
    """)
    assert listar_assuntos(2026, [7], 'Financeiro')['assunto'].tolist() == ['Cobrança']
    assert listar_grupos(2026, [7], 'Financeiro', 'Cobrança')['grupo'].tolist() == ['Valores']
    data = carregar_problemas(2026, [7], 'Financeiro', 'Cobrança', 'Valores', nivel='problemas')
    assert set(data) == {'indicadores', 'problemas'}
    assert data['indicadores'].iloc[0]['reclamacoes'] == 2
    assert data['problemas'].iloc[0]['problemas'] == 'Cobrança indevida'
    assert carregar_problemas(2026, [7], assunto="' OR TRUE --", nivel='assuntos')['indicadores'].iloc[0]['reclamacoes'] == 0
    assert listar_assuntos(2026, [8], 'Financeiro').empty


def test_geography_kpis_match_reference_with_repeated_normalized_cities(dashboard_database):
    from pathlib import Path
    from sqlalchemy import text
    from dashboard.services.specialized import carregar_geografia
    # Mesmo município/UF em dois IDs históricos, com espaços diferentes.
    dashboard_database("""
        INSERT INTO warehouse.dim_localidade (uf, cidade) VALUES ('SP', ' São Paulo ');
        INSERT INTO warehouse.fato_reclamacao (empresa_id, localidade_id, data_id, classificacao_id)
        SELECT f.empresa_id, l.localidade_id, f.data_id, f.classificacao_id
        FROM warehouse.fato_reclamacao f CROSS JOIN warehouse.dim_localidade l
        WHERE f.data_id=20260701 AND l.cidade=' São Paulo ';
    """)
    reference = (Path(__file__).resolve().parents[1] / 'sql/analytics/geography_kpis_reference.sql').read_text()
    engine = create_engine(dashboard_database.connection_url)
    try:
        with engine.connect() as connection:
            for months, uf in [([7], None), ([7, 8], None), ([7], 'SP'), ([7], 'AC'), ([9], None)]:
                expected = dict(connection.execute(text(reference),
                    {'ano': 2026, 'meses': months, 'uf': uf}).mappings().one())
                current = carregar_geografia(2026, months, uf)['indicadores'].iloc[0].to_dict()
                assert current == expected
                if months == [7] and uf is None:
                    assert current == {'reclamacoes': 5, 'ufs': 3, 'cidades': 3}
    finally:
        engine.dispose()


def test_invalid_times_are_excluded_consistently_without_deleting_facts(dashboard_database):
    from dashboard.services.companies import carregar_empresa
    from dashboard.services.specialized import carregar_atendimento
    dashboard_database("UPDATE warehouse.fato_reclamacao SET tempo_resposta=-4 WHERE data_id=20260701")
    overview_data = overview.carregar_visao_geral(2026, [7])['indicadores'].iloc[0]
    service_data = carregar_atendimento(2026, [7])
    for row in [overview_data, service_data['indicadores'].iloc[0], service_data['mensal'].iloc[0]]:
        assert row['tempo_medio'] == 20
        assert row['base_tempo'] == 1
        assert row['tempos_invalidos'] == 1
        assert row['reclamacoes'] == 4
    company = carregar_empresa(2026, [7], 'Empresa')['indicadores'].iloc[0]
    assert pd.isna(company['tempo_medio']) and company['base_tempo'] == 0
    assert company['tempos_invalidos'] == 1
    assert dashboard_database('SELECT tempo_resposta FROM warehouse.fato_reclamacao WHERE data_id=20260701') == '-4'
