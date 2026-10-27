"""Auditoria das execuções mensais da camada Gold."""

from datetime import date

from sqlalchemy import text

from src.database.connection import get_engine

from src.database.gold_lock import gold_execution_lock


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

        # ============================================================
# RECUPERAÇÃO DE EXECUÇÕES INTERROMPIDAS
# ============================================================

RECOVER_INTERRUPTED = text("""
    UPDATE metadata.gold_load_control
       SET status = 'FAILED',
           finalizado_em = CURRENT_TIMESTAMP,
           mensagem_erro = (
               'Execução marcada como FAILED por recuperação '
               'administrativa após exceder o tempo limite.'
           )
     WHERE status = 'RUNNING'
       AND iniciado_em < (
           CURRENT_TIMESTAMP - (
               CAST(:timeout_minutes AS INTEGER) * INTERVAL '1 minute'
           )
       )
    RETURNING execution_id
""")



def recover_interrupted_executions(
    timeout_minutes: int = 60,
) -> list[int]:
    """
    Recupera execuções RUNNING que ultrapassaram
    o tempo limite.

    A recuperação só ocorre quando nenhuma outra
    operação protegida pelo Advisory Lock está ativa.

    Retorna os IDs das execuções recuperadas.
    """

    if (
        isinstance(timeout_minutes, bool)
        or not isinstance(timeout_minutes, int)
        or timeout_minutes <= 0
    ):
        raise ValueError(
            "timeout_minutes deve ser um inteiro positivo."
        )

    # Usa o mesmo bloqueio exclusivo da pipeline.
    with gold_execution_lock():

        engine = get_engine()

        try:
            with engine.begin() as connection:
                result = connection.execute(
                    RECOVER_INTERRUPTED,
                    {
                        "timeout_minutes": timeout_minutes,
                    },
                )

                recovered_ids = result.scalars().all()

            return recovered_ids

        finally:
            engine.dispose()



def main():
    """CLI administrativa; subcomando explícito para evitar alterações acidentais."""
    import argparse
    parser = argparse.ArgumentParser(description="Administração da auditoria Gold.")
    commands = parser.add_subparsers(dest="command", required=True)
    recover = commands.add_parser("recover", help="Marca execuções antigas RUNNING como FAILED.")
    recover.add_argument("--timeout-minutes", type=int, default=60)
    args = parser.parse_args()
    if args.timeout_minutes <= 0:
        parser.error("--timeout-minutes deve ser um inteiro positivo.")
    print("Execuções recuperadas:", recover_interrupted_executions(args.timeout_minutes))


if __name__ == "__main__":
    main()
