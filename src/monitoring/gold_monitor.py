
"""Monitoramento operacional da camada Gold."""

import argparse

from sqlalchemy import text

from src.database.connection import get_engine


MONITORING_SQL = text("""
    SELECT
        COUNT(*) AS total_execucoes,

        COUNT(*) FILTER (
            WHERE status = 'SUCCESS'
        ) AS sucessos,

        COUNT(*) FILTER (
            WHERE status = 'FAILED'
        ) AS falhas,

        COUNT(*) FILTER (
            WHERE status = 'RUNNING'
        ) AS em_execucao,

        ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE status = 'SUCCESS'
            ) / NULLIF(COUNT(*), 0),
            2
        ) AS taxa_sucesso_percentual,

        ROUND(
            AVG(
                EXTRACT(
                    EPOCH FROM (finalizado_em - iniciado_em)
                )
            ) FILTER (
                WHERE status = 'SUCCESS'
            )::numeric,
            2
        ) AS duracao_media_sucesso_segundos,

        MAX(finalizado_em) FILTER (
            WHERE status = 'SUCCESS'
        ) AS ultima_execucao_sucesso

    FROM metadata.gold_load_control
""")


def get_gold_metrics():
    """Consulta os indicadores da Gold sem modificar os dados."""
    engine = get_engine()

    try:
        with engine.connect() as connection:
            result = connection.execute(MONITORING_SQL)
            return dict(result.mappings().one())
    finally:
        engine.dispose()


def format_value(value, suffix=""):
    if value is None:
        return "N/D"
    return f"{value}{suffix}"


def show_gold_metrics():
    """Exibe os indicadores operacionais no terminal."""
    metrics = get_gold_metrics()

    print("\n" + "=" * 60)
    print("E-COMMERCE COMPLAINT INTELLIGENCE PLATFORM")
    print("MONITORAMENTO DA CAMADA GOLD")
    print("=" * 60)

    print(f"Total de execuções: {metrics['total_execucoes']}")
    print(f"Sucessos:           {metrics['sucessos']}")
    print(f"Falhas:             {metrics['falhas']}")
    print(f"Em execução:        {metrics['em_execucao']}")

    print(
        "Taxa de sucesso:    "
        + format_value(metrics["taxa_sucesso_percentual"], "%")
    )

    print(
        "Duração média:      "
        + format_value(
            metrics["duracao_media_sucesso_segundos"], " segundos"
        )
    )

    print(
        "Último sucesso:     "
        + format_value(metrics["ultima_execucao_sucesso"])
    )

    print("=" * 60)


def get_gold_history(limit=10):
    """Consulta as execuções mais recentes da camada Gold."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("O limite deve ser um inteiro positivo.")

    query = text("""
        SELECT
            execution_id,
            periodo,
            status,
            registros_staging,
            registros_gold,
            iniciado_em,
            finalizado_em,
            ROUND(
                EXTRACT(
                    EPOCH FROM (finalizado_em - iniciado_em)
                )::numeric,
                2
            ) AS duracao_segundos,
            mensagem_erro
        FROM metadata.gold_load_control
        ORDER BY iniciado_em DESC, execution_id DESC
        LIMIT :limit
    """)

    engine = get_engine()

    try:
        with engine.connect() as connection:
            result = connection.execute(query, {"limit": limit})
            return [dict(row) for row in result.mappings().all()]
    finally:
        engine.dispose()


def show_gold_history(limit=10):
    """Exibe o histórico recente de execuções."""
    history = get_gold_history(limit)

    print("\n" + "=" * 60)
    print("HISTÓRICO DE EXECUÇÕES DA GOLD")
    print("=" * 60)

    if not history:
        print("Nenhuma execução encontrada.")
        return

    for execution in history:
        print(f"\nExecução: {execution['execution_id']}")
        print(f"Período:  {execution['periodo']}")
        print(f"Status:   {execution['status']}")
        print(f"Staging:  {format_value(execution['registros_staging'])}")
        print(f"Gold:     {format_value(execution['registros_gold'])}")
        print(
            "Duração:  "
            + format_value(execution["duracao_segundos"], " segundos")
        )

        if execution["mensagem_erro"]:
            print(f"Erro:     {execution['mensagem_erro']}")

        print("-" * 60)



def main():
    parser = argparse.ArgumentParser(
        description="Monitoramento operacional da camada Gold."
    )

    parser.add_argument(
        "--history",
        action="store_true",
        help="Exibe o histórico recente de execuções."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Quantidade máxima de execuções no histórico (padrão: 10)."
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit deve ser um inteiro positivo.")

    show_gold_metrics()

    if args.history:
        show_gold_history(args.limit)



if __name__ == "__main__":
    main()
