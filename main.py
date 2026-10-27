
import argparse
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.database.gold_lock import gold_execution_lock
from src.database.load_gold import load_gold
from src.database.load_staging import run as load_staging
from src.ingestion.download_complaints import run as ingest_local
from src.transformation.transform_complaints import run as transform


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def get_arguments():
    """Valida os argumentos da execução."""

    parser = argparse.ArgumentParser(
        description=(
            "Pipeline de Engenharia de Dados do "
            "E-commerce Complaint Intelligence Platform."
        )
    )

    parser.add_argument(
        "period",
        help="Período no formato YYYY-MM.",
    )

    parser.add_argument(
        "--source",
        choices=["local", "minio"],
        default="minio",
        help="Origem Bronze. Padrão: minio.",
    )

    parser.add_argument(
        "--skip-gold",
        action="store_true",
        help="Não carrega a Gold.",
    )

    args = parser.parse_args()

    if not re.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])",
        args.period,
    ):
        parser.error(
            "Período inválido. Utilize YYYY-MM."
        )

    return args


def main():
    """
    Orquestra a pipeline completa.

    O Advisory Lock protege todas as etapas,
    impedindo duas execuções simultâneas
    que utilizem o mesmo bloqueio.
    """

    args = get_arguments()

    start = time.perf_counter()

    print(f"\n{'=' * 70}")
    print("E-COMMERCE COMPLAINT INTELLIGENCE PLATFORM")
    print(f"{'=' * 70}")
    print(f"Período:       {args.period}")
    print(f"Origem Bronze: {args.source.upper()}")
    print(
        f"Carga Gold:    "
        f"{'NÃO' if args.skip_gold else 'SIM'}"
    )
    print(f"{'=' * 70}")

    completed = []

    try:
        # O bloqueio é mantido durante toda a pipeline.
        # A conexão PostgreSQL permanece aberta até
        # o encerramento do contexto.
        with gold_execution_lock():

            print(
                "\n[LOCK] Bloqueio exclusivo "
                "da pipeline adquirido.",
                flush=True,
            )

            # ETAPA 1 - INGESTÃO
            if args.source == "local":
                ingest_local(args.period)
                completed.append("Ingestão local")

            else:
                print(
                    "\n[INFO] Modo MinIO selecionado. "
                    "Consulta à API dispensada."
                )

            # ETAPA 2 - BRONZE -> SILVER
            transform(
                args.period,
                args.source,
                upload=args.source == "minio",
            )

            completed.append(
                "Transformação Bronze -> Silver"
            )

            # ETAPA 3 - SILVER -> STAGING
            load_staging(
                args.period,
                args.source,
            )

            completed.append(
                "Carregamento PostgreSQL Staging"
            )

            # ETAPA 4 - STAGING -> GOLD
            if args.skip_gold:
                print(
                    "\n[INFO] Carga Gold ignorada "
                    "(--skip-gold)."
                )

            else:
                load_gold(args.period)

                completed.append(
                    "Carregamento PostgreSQL Gold"
                )

        # O contexto encerrou e liberou o bloqueio.
        print(
            "[LOCK] Bloqueio exclusivo liberado."
        )

    except Exception as error:
        print(
            f"\n[ERRO] Pipeline interrompida: {error}",
            file=sys.stderr,
        )

        raise SystemExit(1) from error

    print(f"\n{'=' * 70}")
    print("PIPELINE FINALIZADA COM SUCESSO")
    print(
        f"Período: {args.period} "
        f"| Origem: {args.source.upper()}"
    )
    print("Etapas concluídas:")

    for index, step in enumerate(
        completed,
        start=1,
    ):
        print(
            f"  {index}. {step}"
        )

    print(
        f"Tempo total: "
        f"{time.perf_counter() - start:.2f} segundos"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
