"""SQL, rollback e concorrência com fixture compartilhada de banco descartável.

RUN_TEMP_POSTGRES_TESTS=1 usa cluster local; TEST_DB_NAME habilita servidor de testes.
A preparação e limpeza são automáticas nos dois modos.
"""
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


INSERT = """
INSERT INTO staging.complaints
    (data_finalizacao, nome_fantasia, uf, cidade, avaliacao_reclamacao, nota_do_consumidor)
VALUES ('2026-07-01', 'Empresa', 'SP', 'São Paulo', 'Resolvida', 4)
"""


@pytest.fixture
def seeded(postgres):
    sql, load = postgres
    sql('TRUNCATE metadata.gold_load_control, staging.complaints, warehouse.fato_reclamacao, warehouse.dim_empresa, '
        'warehouse.dim_localidade, warehouse.dim_tempo, warehouse.dim_classificacao RESTART IDENTITY')
    sql(INSERT + "; UPDATE staging.complaints SET data_finalizacao='2026-06-01'")
    result = load('2026-06')
    assert result.returncode == 0, result.stderr
    sql('TRUNCATE staging.complaints; ' + INSERT)
    result = load()
    assert result.returncode == 0, result.stderr
    return sql, load


def snapshot(sql):
    """Compara fatos e dimensões completos, incluindo IDs e outro mês."""
    result = {}
    for table in ('fato_reclamacao', 'dim_empresa', 'dim_localidade', 'dim_tempo', 'dim_classificacao'):
        result[table] = json.loads(sql(
            f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '[]'::jsonb) "
            f'FROM warehouse.{table} t'
        ))
    return result


@pytest.mark.parametrize('period', [None, 'invalid', '2026-08'])
def test_rejects_missing_invalid_or_different_period(seeded, period):
    sql, load = seeded
    before = snapshot(sql)
    assert load(period).returncode != 0
    assert snapshot(sql) == before


@pytest.mark.parametrize('change', [
    "uf='XX'", 'nota_do_consumidor=6', 'nota_do_consumidor=NULL',
    "avaliacao_reclamacao='Não Avaliada'", "nome_fantasia=' '", 'data_finalizacao=NULL',
])
def test_quality_rejection_preserves_warehouse(seeded, change):
    sql, load = seeded
    before = snapshot(sql)
    sql('UPDATE staging.complaints SET ' + change)
    assert load().returncode != 0
    assert snapshot(sql) == before


@pytest.mark.parametrize('mixed', [False, True])
def test_empty_or_mixed_month_staging_preserves_warehouse(seeded, mixed):
    sql, load = seeded
    before = snapshot(sql)
    if mixed:
        sql(INSERT + "; UPDATE staging.complaints SET data_finalizacao='2026-08-01' "
            "WHERE ctid = (SELECT ctid FROM staging.complaints LIMIT 1)")
    else:
        sql('TRUNCATE staging.complaints')
    assert load().returncode != 0
    assert snapshot(sql) == before


def test_failure_after_delete_rolls_back_facts_and_dimensions(seeded):
    sql, load = seeded
    before = snapshot(sql)
    sql("UPDATE staging.complaints SET nome_fantasia='Nova empresa'")
    sql("""
        CREATE FUNCTION warehouse.reject_test_insert() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Falha controlada depois do DELETE'; END $$;
        CREATE TRIGGER reject_test_insert BEFORE INSERT ON warehouse.fato_reclamacao
        FOR EACH ROW EXECUTE FUNCTION warehouse.reject_test_insert();
    """)
    try:
        result = load()
        assert result.returncode != 0
        assert 'Falha controlada depois do DELETE' in result.stderr
        assert snapshot(sql) == before
    finally:
        sql('DROP TRIGGER reject_test_insert ON warehouse.fato_reclamacao; '
            'DROP FUNCTION warehouse.reject_test_insert()')


def test_reprocessing_preserves_business_data_and_other_month(seeded):
    sql, load = seeded
    before = snapshot(sql)
    result = load()
    assert result.returncode == 0, result.stderr
    after = snapshot(sql)
    june_before = [row for row in before['fato_reclamacao'] if row['data_id'] == 20260601]
    june_after = [row for row in after['fato_reclamacao'] if row['data_id'] == 20260601]
    assert june_after == june_before
    for state in (before, after):
        for fact in state['fato_reclamacao']:
            fact.pop('reclamacao_id')  # Idempotência lógica; a identity pode avançar.
    assert after == before


@pytest.fixture
def operation_database(seeded, monkeypatch):
    from sqlalchemy import create_engine
    from src.database import gold_lock, gold_audit, load_staging
    sql, load = seeded
    def engine():
        return create_engine(sql.connection_url)
    for module in (gold_lock, gold_audit, load_staging):
        monkeypatch.setattr(module, 'get_engine', engine)
    return sql, load, engine


@pytest.mark.parametrize('command', [
    ['main.py', '2026-07', '--source', 'local'],
    ['-m', 'src.database.load_staging', '2026-07'],
    ['-m', 'src.database.load_gold', '2026-07'],
    ['-m', 'src.transformation.transform_complaints', '2026-07'],
    ['-m', 'src.ingestion.download_complaints', '2026-07'],
    ['-m', 'src.ingestion.backfill', '--year', '2026', '--start-month', '7', '--end-month', '7'],
    ['-m', 'src.storage.sync_data_lake', 'silver', '2026-07'],
    ['-m', 'src.storage.download_from_minio', 'silver', '2026-07'],
    ['scripts/prepare_bronze_zip.py', '2026-07', '/tmp/absent-source.zip'],
    ['scripts/download_direct.py', '--json', '/tmp/absent-catalog.json'],
    ['-m', 'src.database.gold_audit', 'recover', '--timeout-minutes', '60'],
])
def test_competing_process_commands_are_rejected(operation_database, command, tmp_path):
    import sys
    from src.database.gold_lock import gold_execution_lock
    sql, load, engine = operation_database
    # O download direto lê o catálogo antes de começar os downloads protegidos.
    if command[0] == 'scripts/download_direct.py':
        catalog = tmp_path / 'catalog.json'
        catalog.write_text(json.dumps([{
            'texto': 'Arquivo em formato CSV com dados de todas as reclamações finalizadas',
            'nomeArquivo': 'finalizadas_2026-07.zip', 'codigo': 123,
        }]))
        command = [*command[:2], str(catalog), '--destino', str(tmp_path / 'download')]
    env = {**os.environ, **sql.environment, 'PIPELINE_LOCK_HELD': '1'}  # Variável inventada não concede dispensa de lock.
    before = snapshot(sql)
    audit_before = sql('SELECT COUNT(*) FROM metadata.gold_load_control')
    with gold_execution_lock():
        result = subprocess.run([sys.executable, *command], env=env, cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        assert result.returncode != 0
        assert 'Outra operação Gold está em andamento' in result.stdout + result.stderr
    assert snapshot(sql) == before
    assert sql('SELECT COUNT(*) FROM metadata.gold_load_control') == audit_before


def test_direct_sql_is_rejected_while_python_holds_lock(operation_database):
    from src.database.gold_lock import gold_execution_lock
    sql, load, engine = operation_database
    before = snapshot(sql)
    with gold_execution_lock():
        result = load()
        assert result.returncode != 0
        assert 'Outra operação Gold está em andamento' in result.stderr
    assert snapshot(sql) == before
    assert load().returncode == 0


def test_sql_transaction_lock_rejects_python(operation_database):
    from sqlalchemy import text
    from src.database.gold_lock import gold_execution_lock
    sql, load, factory = operation_database
    engine = factory()
    try:
        with engine.begin() as connection:
            assert connection.execute(text('SELECT pg_try_advisory_xact_lock(20261020::bigint)')).scalar_one()
            with pytest.raises(RuntimeError, match='Outra operação Gold'):
                with gold_execution_lock():
                    pytest.fail('Lock não pode ser adquirido')
        with gold_execution_lock():
            pass
    finally:
        engine.dispose()


def test_sql_body_requires_lock_in_own_session(operation_database):
    sql, load, engine = operation_database
    result = sql.run(sql.psql_prefix + ['-f', ROOT / 'sql/warehouse/load_star_schema_body.sql'])
    assert result.returncode != 0
    assert 'Carga Gold requer o Advisory Lock' in result.stderr


def test_local_pipeline_reuses_lock_and_audits_gold(operation_database, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from zipfile import ZipFile
    import main
    from src.database import load_staging
    from src.database.gold_lock import gold_execution_lock
    from src.ingestion import download_complaints
    from src.transformation import transform_complaints
    from tests.test_pipeline_quality import raw_frame
    sql, load, factory = operation_database
    june = sql('SELECT row_to_json(f)::text FROM warehouse.fato_reclamacao f WHERE data_id=20260601')
    with ZipFile(tmp_path / 'finalizadas_2026-07.zip', 'w') as archive:
        archive.writestr('sub/finalizadas_2026-07.csv', raw_frame().to_csv(index=False, sep=';'))
    monkeypatch.setattr(download_complaints, 'RAW_DIR', tmp_path)
    monkeypatch.setattr(transform_complaints, 'RAW_DIR', tmp_path)
    monkeypatch.setattr(transform_complaints, 'PROCESSED_DIR', tmp_path)
    monkeypatch.setattr(load_staging, 'PROCESSED_DIR', tmp_path)
    monkeypatch.setattr(main, 'get_arguments', lambda: SimpleNamespace(period='2026-07', source='local', skip_gold=False))
    main.main()
    main.main()
    assert sql("SELECT COUNT(*) FROM metadata.gold_load_control WHERE status='SUCCESS'") == '2'
    assert sql("SELECT COUNT(*) FROM warehouse.fato_reclamacao WHERE data_id=20260701") == '1'
    assert sql('SELECT row_to_json(f)::text FROM warehouse.fato_reclamacao f WHERE data_id=20260601') == june
    with gold_execution_lock():
        pass  # Liberação ao final da pipeline permite operação seguinte.


def test_failed_python_gold_rolls_back_and_releases_lock(operation_database):
    from src.database.load_gold import load_gold
    from src.database.gold_lock import gold_execution_lock
    sql, load, engine = operation_database
    before = snapshot(sql)
    sql("UPDATE staging.complaints SET uf='XX'")
    with pytest.raises(Exception, match='Staging invalida'):
        load_gold('2026-07')
    assert snapshot(sql) == before
    assert sql("SELECT COUNT(*) FROM metadata.gold_load_control WHERE status='FAILED'") == '1'
    with gold_execution_lock():
        pass


def test_minio_pipeline_reuses_lock_for_cache_and_upload(operation_database, monkeypatch, tmp_path):
    from io import BytesIO
    from types import SimpleNamespace
    from zipfile import ZipFile
    import main
    from src.database.gold_lock import gold_execution_lock
    from src.storage import download_from_minio as storage
    from src.transformation import transform_complaints
    from tests.test_pipeline_quality import raw_frame
    sql, load, factory = operation_database
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('finalizadas_2026-07.csv', raw_frame().to_csv(index=False, sep=';'))
    bronze_key = 'consumidor_gov/ano=2026/mes=07/finalizadas_2026-07.zip'
    silver_key = 'consumidor_gov/ano=2026/mes=07/complaints_2026-07.parquet'
    objects = {('ecommerce-bronze', bronze_key): buffer.getvalue()}
    class Minio:
        def head_object(self, Bucket, Key):
            return {'ContentLength': len(objects[(Bucket, Key)])}
        def download_file(self, bucket, key, destination):
            Path(destination).write_bytes(objects[(bucket, key)])
        def upload_file(self, source, bucket, key):
            objects[(bucket, key)] = Path(source).read_bytes()
    client = Minio()
    monkeypatch.setattr(storage, 'get_minio_client', lambda: client)
    monkeypatch.setattr(transform_complaints, 'get_minio_client', lambda: client)
    monkeypatch.setattr(storage, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(transform_complaints, 'PROCESSED_DIR', tmp_path / 'processed')
    monkeypatch.setattr(main, 'get_arguments', lambda: SimpleNamespace(period='2026-07', source='minio', skip_gold=False))
    main.main()
    assert ('ecommerce-silver', silver_key) in objects
    assert sql("SELECT COUNT(*) FROM metadata.gold_load_control WHERE status='SUCCESS'") == '1'
    assert sql('SELECT COUNT(*) FROM warehouse.fato_reclamacao') == '2'
    with gold_execution_lock():
        pass


def test_recovery_cli_updates_only_stale_running_audit(operation_database):
    import sys
    from src.database.gold_lock import gold_execution_lock
    sql, load, factory = operation_database
    sql("""
        INSERT INTO metadata.gold_load_control (periodo, status, registros_staging, iniciado_em)
        VALUES ('2026-07-01', 'RUNNING', 1, CURRENT_TIMESTAMP - INTERVAL '2 hours'),
               ('2026-07-01', 'RUNNING', 1, CURRENT_TIMESTAMP);
    """)
    env = {**os.environ, **sql.environment}
    result = subprocess.run(
        [sys.executable, '-m', 'src.database.gold_audit', 'recover', '--timeout-minutes', '60'],
        env=env, cwd=ROOT, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert sql("SELECT COUNT(*) FROM metadata.gold_load_control WHERE status='FAILED'") == '1'
    assert sql("SELECT COUNT(*) FROM metadata.gold_load_control WHERE status='RUNNING'") == '1'
    with gold_execution_lock():
        pass


def test_staging_ddl_and_insert_failure_roll_back(operation_database, monkeypatch, tmp_path):
    from src.database import load_staging
    from src.database.gold_lock import gold_execution_lock
    from src.transformation.transform_complaints import transform
    from tests.test_pipeline_quality import raw_frame
    sql, load, factory = operation_database
    before = sql('SELECT row_to_json(c)::text FROM staging.complaints c ORDER BY data_finalizacao')
    table_oid = sql("SELECT 'staging.complaints'::regclass::oid")
    warehouse = snapshot(sql)
    frame = raw_frame()
    frame['Cidade'] = 'Cidade sintética nova'
    parquet = tmp_path / 'silver.parquet'
    transform(frame).to_parquet(parquet, index=False)
    monkeypatch.setattr(load_staging, 'get_silver_file', lambda *args: parquet)
    original_insert = load_staging.insert_data
    def failed_insert(data, connection):
        original_insert(data, connection)
        raise RuntimeError('Falha controlada após recriar e inserir na Staging')
    monkeypatch.setattr(load_staging, 'insert_data', failed_insert)
    with pytest.raises(RuntimeError, match='Falha controlada'):
        load_staging.run('2026-07', 'local')
    assert sql('SELECT row_to_json(c)::text FROM staging.complaints c ORDER BY data_finalizacao') == before
    assert sql("SELECT 'staging.complaints'::regclass::oid") == table_oid
    assert snapshot(sql) == warehouse
    with gold_execution_lock():
        pass


def test_initializer_refuses_existing_schema_without_changing_data(seeded):
    sql, load = seeded
    before = snapshot(sql)
    result = sql.run(sql.psql_prefix + ['-f', ROOT / 'sql/init_database.sql'])
    assert result.returncode != 0
    assert 'Inicialização recusada' in result.stderr
    assert snapshot(sql) == before
