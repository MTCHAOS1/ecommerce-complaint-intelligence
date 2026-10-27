"""Carga Gold auditada e protegida, avulsa ou dentro da pipeline."""
import argparse
from pathlib import Path
import re
import sys
import time

from sqlalchemy import text

from src.database.gold_audit import (
    count_gold_records, fail_gold_execution, finish_gold_execution, start_gold_execution,
)
from src.database.gold_lock import exclusive_operation, pipeline_operation

GOLD_SQL_FILE = Path(__file__).resolve().parents[2] / "sql/warehouse/load_star_schema_body.sql"


@exclusive_operation
def load_gold(period):
    """
    Executa a carga Gold e registra sua auditoria.

    A auditoria utiliza transações independentes
    da transação executada pelo script SQL.
    """

    if not GOLD_SQL_FILE.is_file():
        raise FileNotFoundError(
            f"Script Gold não encontrado: {GOLD_SQL_FILE}"
        )

    execution_id, staging_count = start_gold_execution(period)

    print(
        f"[AUDITORIA] Execução {execution_id}: RUNNING "
        f"| Staging: {staging_count:,}"
    )

    try:
        started = time.perf_counter()
        sql = GOLD_SQL_FILE.read_text(encoding="utf-8")
        # A sessão que mantém o Advisory Lock executa a própria transação Gold.
        with pipeline_operation() as connection:
            with connection.begin():
                connection.execute(
                    text("SELECT set_config('app.expected_period', :period, true)"),
                    {"period": period},
                )
                connection.exec_driver_sql(sql, execution_options={"no_parameters": True})
        elapsed = time.perf_counter() - started

        gold_count = count_gold_records(period)

        if gold_count != staging_count:
            raise RuntimeError(
                "Divergência após COMMIT: "
                f"Staging={staging_count}, "
                f"Gold={gold_count}"
            )

        finish_gold_execution(
            execution_id,
            gold_count,
        )

        print(
            f"[AUDITORIA] Execução {execution_id}: SUCCESS "
            f"| Gold: {gold_count:,}"
        )

        return elapsed

    except Exception as error:
        try:
            fail_gold_execution(
                execution_id,
                error,
            )

            print(
                f"[AUDITORIA] Execução {execution_id}: FAILED"
            )

        except Exception as audit_error:
            print(
                "[ERRO] Falha também ao registrar FAILED: "
                f"{audit_error}",
                file=sys.stderr,
            )

        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("period", help="Período YYYY-MM da Staging já preparada.")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", args.period):
        parser.error("Período inválido. Utilize YYYY-MM.")
    load_gold(args.period)


if __name__ == "__main__":
    main()
