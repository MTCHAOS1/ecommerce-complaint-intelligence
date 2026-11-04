"""Atualização recorrente Bronze → Gold, com retomada por mês auditado."""
import argparse
from datetime import date
import logging
import time

from sqlalchemy import text

from src.database.gold_lock import pipeline_operation
from src.database.load_gold import load_gold
from src.database.load_staging import run as load_staging
from src.ingestion.backfill import run_backfill
from src.quality.monthly_periods import month_number, select_periods
from src.transformation.transform_complaints import run as transform


logger = logging.getLogger(__name__)

COMPLETED_PERIOD_SQL = text("""
    WITH latest AS (
        SELECT status, registros_staging, registros_gold
        FROM metadata.gold_load_control
        WHERE periodo = :period
        ORDER BY execution_id DESC LIMIT 1
    ), actual AS (
        SELECT COUNT(*) AS total
        FROM warehouse.fato_reclamacao f
        JOIN warehouse.dim_tempo t USING (data_id)
        WHERE t.ano = :year AND t.mes = :month
    )
    SELECT EXISTS (
        SELECT 1 FROM latest, actual
        WHERE status = 'SUCCESS' AND total > 0
          AND registros_gold = total AND registros_staging = total
    )
""")


def is_complete(connection, period):
    """Exige última auditoria SUCCESS e contagens positivas compatíveis com a Gold."""
    year, month = map(int, period.split('-'))
    parameters = {'period': date(year, month, 1), 'year': year, 'month': month}
    with connection.begin():
        result = connection.execute(COMPLETED_PERIOD_SQL, parameters)
        return bool(result.scalar_one())


def _refresh_period(period):
    """Carrega um mês até a Gold somente quando a Bronze está disponível."""
    year, month = map(int, period.split('-'))
    if not run_backfill(year, month, month, 0):
        return 'PENDING'

    transform(period, 'minio', upload=True)
    load_staging(period, 'minio')
    load_gold(period)
    return 'SUCCESS'


def refresh(periods, *, reprocess=False, delay=5.0):
    """Continua outros meses após falhas; retorna o resultado de cada período."""
    if not periods or not 0 <= delay <= 3600:
        raise ValueError('Informe períodos e delay entre 0 e 3600 segundos.')
    # Valida toda a entrada antes de adquirir lock ou modificar qualquer camada.
    for period in periods:
        month_number(period)
    results = {}
    with pipeline_operation() as connection:
        attempted = False
        for period in periods:
            try:
                if not reprocess and is_complete(connection, period):
                    results[period] = 'SKIPPED'
                    continue
                if attempted and delay:
                    time.sleep(delay)
                attempted = True
                results[period] = _refresh_period(period)
            except Exception:
                logger.exception('Falha na atualização de %s', period)
                results[period] = 'FAILED'
            finally:
                logger.info('%s: %s', period, results.get(period, 'FAILED'))
    return results


def _argument_parser():
    """Define a interface de linha de comando sem acessar os serviços."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', help='Primeiro mês encerrado: YYYY-MM.')
    parser.add_argument('--end', help='Último mês encerrado: YYYY-MM.')
    parser.add_argument(
        '--lookback', type=int, default=3,
        help='Meses encerrados revistos sem intervalo explícito (padrão: 3).',
    )
    parser.add_argument(
        '--delay', type=float, default=5,
        help='Segundos entre meses que precisam de processamento (0–3600).',
    )
    parser.add_argument(
        '--reprocess', action='store_true', help='Recarrega também meses auditados.',
    )
    parser.add_argument(
        '--plan', action='store_true', help='Lista meses sem conectar aos serviços.',
    )
    return parser


def main():
    parser = _argument_parser()
    args = parser.parse_args()
    try:
        periods = select_periods(args.start, args.end, args.lookback)
        if not 0 <= args.delay <= 3600:
            raise ValueError('--delay deve estar entre 0 e 3600 segundos.')
    except ValueError as error:
        parser.error(str(error))
    print('Períodos: ' + ', '.join(periods), flush=True)
    if args.plan:
        return
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    try:
        results = refresh(periods, reprocess=args.reprocess, delay=args.delay)
    except Exception:
        logger.exception('Atualização interrompida.')
        raise SystemExit(1)
    if any(status not in ('SUCCESS', 'SKIPPED') for status in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
