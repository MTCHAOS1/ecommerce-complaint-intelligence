"""Auditoria das execuções mensais da camada Gold."""

from datetime import date

from sqlalchemy import text

from src.database.connection import get_engine


INSERT_RUNNING = text("""
    INSERT INTO metadata.gold_load_control
        (periodo, status, registros_staging)
    VALUES (:periodo, 'RUNNING', :registros_staging)
    RETURNING execution_id
""")

UPDATE_SUCCESS = text("""
    UPDATE metadata.gold_load_control
       SET status = 'SUCCESS',
           registros_gold = :registros_gold,
           finalizado_em = CURRENT_TIMESTAMP,
           mensagem_erro = NULL
     WHERE execution_id = :execution_id
       AND status = 'RUNNING'
""")

UPDATE_FAILED = text("""
    UPDATE metadata.gold_load_control
       SET status = 'FAILED',
           finalizado_em = CURRENT_TIMESTAMP,
           mensagem_erro = :mensagem_erro
     WHERE execution_id = :execution_id
       AND status = 'RUNNING'
""")

COUNT_STAGING = text("SELECT COUNT(*) FROM staging.complaints")

COUNT_GOLD = text("""
    SELECT COUNT(*)
      FROM warehouse.fato_reclamacao AS fato
      JOIN warehouse.dim_tempo AS tempo ON tempo.data_id = fato.data_id
     WHERE tempo.ano = :ano AND tempo.mes = :mes
""")


def start_gold_execution(period: str) -> tuple[int, int]:
    """Registra RUNNING em transação própria e devolve ID e total Staging."""
    year, month = map(int, period.split("-"))
    period_date = date(year, month, 1)
    engine = get_engine()
    try:
        with engine.begin() as connection:
            staging_count = connection.execute(COUNT_STAGING).scalar_one()
            # A Staging é validada previamente pelo carregador Python.
            execution_id = connection.execute(
                INSERT_RUNNING,
                {"periodo": period_date, "registros_staging": staging_count},
            ).scalar_one()
        return execution_id, staging_count
    finally:
        engine.dispose()


def count_gold_records(period: str) -> int:
    year, month = map(int, period.split("-"))
    engine = get_engine()
    try:
        with engine.connect() as connection:
            return connection.execute(
                COUNT_GOLD, {"ano": year, "mes": month}
            ).scalar_one()
    finally:
        engine.dispose()


def finish_gold_execution(execution_id: int, gold_count: int) -> None:
    engine = get_engine()
    try:
        with engine.begin() as connection:
            result = connection.execute(
                UPDATE_SUCCESS,
                {"execution_id": execution_id, "registros_gold": gold_count},
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Execução {execution_id} não está RUNNING")
    finally:
        engine.dispose()


def fail_gold_execution(execution_id: int, error: BaseException) -> None:
    engine = get_engine()
    try:
        with engine.begin() as connection:
            result = connection.execute(
                UPDATE_FAILED,
                {"execution_id": execution_id, "mensagem_erro": str(error)[:4000]},
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Execução {execution_id} não está RUNNING")
    finally:
        engine.dispose()
