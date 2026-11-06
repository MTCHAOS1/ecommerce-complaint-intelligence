"""Diagnóstico somente leitura da cobertura e das cargas de um intervalo mensal."""

import argparse
from datetime import date
import json
import sys

from sqlalchemy import text

from src.database.connection import get_engine
from src.quality.monthly_periods import select_periods


COVERAGE_SQL = text("""
    WITH months AS (
        SELECT month::date AS periodo
        FROM generate_series(CAST(:start AS date), CAST(:end AS date),
                             INTERVAL '1 month') AS month
    ), counts AS (
        SELECT MAKE_DATE(t.ano, t.mes, 1) AS periodo, COUNT(*) AS registros_gold,
               COUNT(*) FILTER (WHERE nota_do_consumidor NOT IN (1,2,3,4,5)
                    OR tempo_resposta < 0
                    OR tempo_resposta IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) AS registros_invalidos
        FROM warehouse.fato_reclamacao f
        JOIN warehouse.dim_tempo t USING (data_id)
        WHERE t.data >= :start AND t.data < CAST(:end AS date) + INTERVAL '1 month'
        GROUP BY t.ano, t.mes
    ), successes AS (
        SELECT periodo, MAX(finalizado_em) AS ultima_carga_sucesso
        FROM metadata.gold_load_control
        WHERE periodo BETWEEN :start AND :end AND status = 'SUCCESS'
        GROUP BY periodo
    )
    SELECT m.periodo, COALESCE(c.registros_gold, 0) AS registros_gold,
           COALESCE(c.registros_invalidos, 0) AS registros_invalidos,
           a.execution_id, a.status AS ultima_situacao,
           a.registros_staging AS registros_staging_auditados,
           a.registros_gold AS registros_gold_auditados,
           a.iniciado_em, a.finalizado_em, s.ultima_carga_sucesso
    FROM months m
    LEFT JOIN counts c USING (periodo)
    LEFT JOIN successes s USING (periodo)
    LEFT JOIN LATERAL (
        SELECT execution_id, status, registros_staging, registros_gold,
               iniciado_em, finalizado_em
        FROM metadata.gold_load_control
        WHERE periodo = m.periodo
        ORDER BY execution_id DESC LIMIT 1
    ) a ON TRUE
    ORDER BY m.periodo
""")

LONG_RUNNING_SQL = text("""
    SELECT execution_id, periodo, iniciado_em,
           FLOOR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - iniciado_em)))::bigint
               AS duracao_segundos
    FROM metadata.gold_load_control
    WHERE periodo BETWEEN :start AND :end AND status = 'RUNNING'
      AND iniciado_em < CURRENT_TIMESTAMP - :timeout * INTERVAL '1 minute'
    ORDER BY iniciado_em, execution_id
""")


def get_gold_health(start, end, timeout_minutes=60):
    """Compara fatos e última auditoria no mesmo snapshot, sem corrigir estados."""
    select_periods(start, end)  # Valida intervalo inteiro antes de conectar.
    if (isinstance(timeout_minutes, bool) or not isinstance(timeout_minutes, int)
            or timeout_minutes < 1):
        raise ValueError('O tempo limite deve ser um inteiro positivo em minutos.')
    parameters = {
        'start': date.fromisoformat(start + '-01'),
        'end': date.fromisoformat(end + '-01'),
        'timeout': timeout_minutes,
    }
    engine = get_engine()
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(text(
                'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'
            ))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SET LOCAL lock_timeout = '3s'"))
            checked_at = connection.execute(text('SELECT CURRENT_TIMESTAMP')).scalar_one()
            periods = [dict(row) for row in connection.execute(
                COVERAGE_SQL, parameters,
            ).mappings()]
            running = [dict(row) for row in connection.execute(
                LONG_RUNNING_SQL, parameters,
            ).mappings()]
    finally:
        engine.dispose()

    alerts = []
    for row in periods:
        codes = []
        if row['registros_invalidos']:
            codes.append('DOMINIO_INVALIDO')
        if row['registros_gold'] == 0:
            codes.append('SEM_DADOS')
        if row['execution_id'] is None:
            codes.append('SEM_AUDITORIA')
        elif row['ultima_situacao'] == 'FAILED':
            codes.append('ULTIMA_CARGA_FALHOU')
        elif row['ultima_situacao'] == 'SUCCESS' and (
            row['registros_gold_auditados'] != row['registros_gold']
            or row['registros_staging_auditados'] != row['registros_gold']
        ):
            codes.append('CONTAGEM_DIVERGENTE')
        alerts.extend({'periodo': row['periodo'], 'codigo': code} for code in codes)
    alerts.extend({
        'periodo': row['periodo'], 'codigo': 'EXECUCAO_PROLONGADA',
        'execution_id': row['execution_id'],
    } for row in running)

    loaded = [row['periodo'] for row in periods if row['registros_gold'] > 0]
    successes = [row['ultima_carga_sucesso'] for row in periods if row['ultima_carga_sucesso']]
    return {
        'verificado_em': checked_at,
        'inicio': start,
        'fim': end,
        'timeout_minutos': timeout_minutes,
        'total_reclamacoes': sum(row['registros_gold'] for row in periods),
        'ultimo_periodo_com_dados': max(loaded, default=None),
        'ultima_carga_sucesso': max(successes, default=None),
        'meses_sem_dados': [row['periodo'] for row in periods if row['registros_gold'] == 0],
        'periodos': periods,
        'execucoes_prolongadas': running,
        'alertas': alerts,
    }


def show_gold_health(report):
    print(f"Cobertura Gold: {report['inicio']} até {report['fim']}")
    print(f"Verificado em: {report['verificado_em'].isoformat()}")
    print(f"Total de reclamações: {report['total_reclamacoes']:,}".replace(',', '.'))
    print(f"Último mês com dados: {report['ultimo_periodo_com_dados'] or 'N/D'}")
    print(f"Última carga SUCCESS no intervalo: {report['ultima_carga_sucesso'] or 'N/D'}")
    for row in report['periodos']:
        print(f"{row['periodo']:%Y-%m} | {row['registros_gold']} reclamações"
              f" | última auditoria: {row['ultima_situacao'] or 'AUSENTE'}")
    print(f"Alertas: {len(report['alertas'])}")
    for alert in report['alertas']:
        execution = f" | execução {alert['execution_id']}" if 'execution_id' in alert else ''
        print(f"{alert['periodo']:%Y-%m} | {alert['codigo']}{execution}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, help='Primeiro mês encerrado: YYYY-MM.')
    parser.add_argument('--end', required=True, help='Último mês encerrado: YYYY-MM.')
    parser.add_argument('--timeout-minutes', type=int, default=60,
                        help='Limite de duração para RUNNING, em minutos (padrão: 60).')
    parser.add_argument('--json', action='store_true', help='Emite somente JSON.')
    parser.add_argument('--check', action='store_true', help='Retorna código 1 se houver alertas.')
    args = parser.parse_args()
    try:
        report = get_gold_health(args.start, args.end, args.timeout_minutes)
    except ValueError as error:
        parser.error(str(error))
    except Exception:
        print('Não foi possível consultar a Gold. Confira conexão, permissões e disponibilidade.',
              file=sys.stderr)
        raise SystemExit(2)
    if args.json:
        print(json.dumps(report, default=lambda value: value.isoformat(), ensure_ascii=False, indent=2))
    else:
        show_gold_health(report)
    if args.check and report['alertas']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
