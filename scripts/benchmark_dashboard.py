"""Mede SELECTs reais do dashboard com EXPLAIN ANALYZE, sem alterar o warehouse.

O relatório usa dados/planos agregados; não inclui URL de conexão ou credenciais.
Os tempos não incluem cache Streamlit. Não limpa caches do servidor ou do SO.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from src.database.connection import get_engine
from dashboard.services.overview import CONSULTAS, parametros_periodo


PERIODOS_SQL = """
    SELECT t.ano, t.mes, COUNT(*) AS total
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
    GROUP BY t.ano, t.mes ORDER BY t.ano, t.mes
"""


def explain_query(connection, sql, parameters):
    if not sql.lstrip().upper().startswith(('SELECT', 'WITH')):
        raise ValueError('Benchmark aceita apenas as consultas de leitura do dashboard.')
    started = perf_counter()
    result = connection.execute(text(
        'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, TIMING OFF, SUMMARY ON) ' + sql
    ), parameters).scalar_one()
    wall_ms = (perf_counter() - started) * 1000
    return result[0], wall_ms


def measure_query(connection, sql, parameters, repetitions, warmup):
    for _ in range(warmup):
        explain_query(connection, sql, parameters)
    samples = []
    for _ in range(repetitions):
        plan, wall_ms = explain_query(connection, sql, parameters)
        samples.append({
            'execution_ms': plan['Execution Time'], 'planning_ms': plan['Planning Time'],
            'wall_ms': round(wall_ms, 3),
            'shared_hits': plan['Plan'].get('Shared Hit Blocks', 0),
            'shared_reads': plan['Plan'].get('Shared Read Blocks', 0),
            'temp_reads': plan['Plan'].get('Temp Read Blocks', 0),
            'temp_writes': plan['Plan'].get('Temp Written Blocks', 0),
            'plan': plan,
        })
    return {
        'sql': sql, 'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(),
        'median_execution_ms': median(sample['execution_ms'] for sample in samples),
        'median_wall_ms': median(sample['wall_ms'] for sample in samples),
        'samples': samples,
    }



def compare_kpis(connection, parameters, repetitions, warmup):
    """Alterna referência e consulta atual; aborta se algum valor for diferente."""
    reference = (ROOT / 'sql/analytics/dashboard_kpis_reference.sql').read_text(encoding='utf-8')
    # O arquivo tem comentários de identificação antes do SELECT.
    reference = '\n'.join(line for line in reference.splitlines() if not line.lstrip().startswith('--'))
    variants = {'reference': reference, 'current': CONSULTAS['indicadores']}
    results = {name: dict(connection.execute(text(sql), parameters).mappings().one())
               for name, sql in variants.items()}
    if results['reference'] != results['current']:
        raise ValueError('KPIs divergentes: comparação de desempenho interrompida.')
    for _ in range(warmup):
        for sql in variants.values():
            explain_query(connection, sql, parameters)
    runs = {name: [] for name in variants}
    for repetition in range(repetitions):
        order = list(variants) if repetition % 2 == 0 else list(reversed(variants))
        for name in order:
            plan, wall_ms = explain_query(connection, variants[name], parameters)
            runs[name].append({'execution_ms': plan['Execution Time'],
                               'wall_ms': round(wall_ms, 3), 'plan': plan})
    return {'results_equal': True, 'results': results['current'], 'sql': variants,
            'median_execution_ms': {name: median(run['execution_ms'] for run in samples)
                                    for name, samples in runs.items()}, 'runs': runs}

def benchmark(connection, year, scenarios, repetitions=3, warmup=1, timeout_ms=60000, compare_reference=False):
    """Usar uma conexão sem transação ativa; todos os SELECTs compartilham snapshot."""
    report = {
        'measured_at_utc': datetime.now(timezone.utc).isoformat(),
        'year': year, 'repetitions': repetitions, 'warmup': warmup,
        'method': 'EXPLAIN ANALYZE BUFFERS, TIMING OFF; sem cache Streamlit; sem limpar caches PostgreSQL/SO',
    }
    with connection.begin():
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        connection.execute(text("SELECT set_config('statement_timeout', :timeout, true)"), {'timeout': str(timeout_ms)})
        connection.execute(text("SELECT set_config('lock_timeout', '3000', true)"))
        report['server'] = dict(connection.execute(text("""
            SELECT current_database() AS database, current_setting('server_version') AS version,
                   current_setting('work_mem') AS work_mem, current_setting('block_size') AS block_size,
                   current_setting('shared_buffers') AS shared_buffers,
                   current_setting('max_parallel_workers_per_gather') AS parallel_workers_per_gather,
                   current_setting('transaction_read_only') AS read_only,
                   pg_database_size(current_database()) AS database_bytes
        """)).mappings().one())
        report['relations'] = [dict(row) for row in connection.execute(text("""
            SELECT c.relname, c.reltuples::bigint AS estimated_rows,
                   pg_relation_size(c.oid) AS heap_bytes, pg_indexes_size(c.oid) AS indexes_bytes,
                   s.last_analyze, s.last_autoanalyze
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_stat_all_tables s ON s.relid=c.oid
            WHERE n.nspname='warehouse' AND c.relkind='r' ORDER BY c.relname
        """)).mappings()]
        report['indexes'] = [dict(row) for row in connection.execute(text("""
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname='warehouse' ORDER BY tablename, indexname
        """)).mappings()]
        report['loaded_periods'] = [dict(row) for row in connection.execute(text(PERIODOS_SQL)).mappings()]
        print('Medindo catálogo de períodos...', flush=True)
        report['periodos'] = measure_query(connection, PERIODOS_SQL, {}, repetitions, warmup)
        report['scenarios'] = {}
        for name, months in scenarios.items():
            parameters = parametros_periodo(year, months)
            scenario = {'parameters': parameters, 'queries': {}}
            for query_name, sql in CONSULTAS.items():
                result = measure_query(connection, sql, parameters, repetitions, warmup)
                scenario['queries'][query_name] = result
                print(f"{name}/{query_name}: {result['median_execution_ms']:.2f} ms (mediana)", flush=True)
            scenario['sum_median_execution_ms'] = sum(
                query['median_execution_ms'] for query in scenario['queries'].values()
            )
            if compare_reference:
                scenario['kpi_comparison'] = compare_kpis(connection, parameters, repetitions, warmup)
            report['scenarios'][name] = scenario
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--months', type=int, nargs='+', required=True, help='Meses para o cenário amplo.')
    parser.add_argument('--single-month', type=int, required=True, help='Mês para o cenário seletivo.')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--timeout-ms', type=int, default=60000)
    parser.add_argument('--compare-kpis', action='store_true', help='Compara KPIs e planos com a referência, alternando a ordem.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 1 or args.warmup < 0 or args.timeout_ms < 1:
        parser.error('Repetições e timeout devem ser positivos; warmup deve ser não negativo.')
    try:
        broad = parametros_periodo(args.year, args.months)['meses']
        single = parametros_periodo(args.year, [args.single_month])['meses']
    except ValueError as error:
        parser.error(str(error))
    if args.output.exists():
        parser.error('Relatório já existe; escolha outro caminho para preservar a medição anterior.')
    engine = get_engine()
    try:
        with engine.connect() as connection:
            report = benchmark(connection, args.year, {'amplo': broad, 'um_mes': single},
                               args.repetitions, args.warmup, args.timeout_ms, args.compare_kpis)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as destination:
            json.dump(report, destination, ensure_ascii=False, indent=2, default=str)
        print(f'Relatório salvo: {args.output}')
    except SQLAlchemyError as error:
        code = getattr(getattr(error, "orig", None), "sqlstate", None) or type(error).__name__
        parser.exit(1, f"Falha no benchmark PostgreSQL ({code}). Confira conexão, permissões e timeout.\n")
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
