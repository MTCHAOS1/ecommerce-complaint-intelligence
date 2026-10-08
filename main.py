
import argparse
import re
import subprocess
import sys
import time

from pathlib import Path


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

POSTGRES_HOST = "localhost"
POSTGRES_USER = "complaints_user"
POSTGRES_DATABASE = "ecommerce_complaints"

GOLD_SQL_FILE = (
    PROJECT_ROOT
    / "sql"
    / "warehouse"
    / "load_star_schema.sql"
)


# ============================================================
# EXECUÇÃO DE COMANDOS
# ============================================================

def run_command(command, step_name):
    """
    Executa uma etapa da pipeline.

    Se o comando falhar, interrompe o processamento.
    """

    print()
    print("=" * 70)
    print(step_name)
    print("=" * 70)

    start = time.perf_counter()

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )

    elapsed = time.perf_counter() - start

    print()
    print(
        f"[OK] {step_name} concluída "
        f"em {elapsed:.2f} segundos."
    )

    return elapsed


# ============================================================
# INGESTÃO LOCAL
# ============================================================

def ingest_local(period):
    """
    Executa o downloader original.

    O downloader reaproveita o ZIP local válido
    quando ele já existe.
    """

    return run_command(
        [
            sys.executable,
            "-m",
            "src.ingestion.download_complaints",
            period,
        ],
        f"INGESTÃO LOCAL -> BRONZE | {period}",
    )


# ============================================================
# TRANSFORMAÇÃO BRONZE -> SILVER
# ============================================================

def transform(period, source):
    """
    Executa a transformação com a origem selecionada.

    No modo MinIO:
      - Baixa a Bronze do MinIO.
      - Transforma com Pandas.
      - Salva o Parquet localmente.
      - Envia o Parquet para a Silver do MinIO.

    No modo local:
      - Utiliza o ZIP em data/raw/.
      - Salva o Parquet em data/processed/.
    """

    command = [
        sys.executable,
        "-m",
        "src.transformation.transform_complaints",
        period,
        "--source",
        source,
    ]

    if source == "minio":
        command.append("--upload-silver")

    return run_command(
        command,
        f"BRONZE -> SILVER | {period} | {source.upper()}",
    )


# ============================================================
# CARREGAMENTO STAGING
# ============================================================



def load_staging(period, source):
    """
    Carrega a Silver no PostgreSQL Staging,
    utilizando a origem selecionada.
    """

    return run_command(
        [
            sys.executable,
            "-m",
            "src.database.load_staging",
            period,
            "--source",
            source,
        ],
        (
            f"SILVER -> POSTGRESQL STAGING "
            f"| {period} | {source.upper()}"
        ),
    )




# ============================================================
# CARREGAMENTO GOLD
# ============================================================

def load_gold():
    """
    Executa o SQL de carga do Data Warehouse.

    A operação continua usando o script SQL
    existente, sem modificar o Star Schema.
    """

    if not GOLD_SQL_FILE.is_file():
        raise FileNotFoundError(
            f"Script Gold não encontrado: {GOLD_SQL_FILE}"
        )

    command = [
        "psql",
        "-h",
        POSTGRES_HOST,
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DATABASE,
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        str(GOLD_SQL_FILE),
    ]

    return run_command(
        command,
        "POSTGRESQL STAGING -> GOLD",
    )


# ============================================================
# VALIDAÇÃO DOS ARGUMENTOS
# ============================================================

def get_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Pipeline de Engenharia de Dados "
            "do E-commerce Complaint Intelligence Platform."
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
        help=(
            "Origem dos dados Bronze. "
            "Padrão: minio."
        ),
    )

    parser.add_argument(
        "--skip-gold",
        action="store_true",
        help=(
            "Executa a pipeline sem carregar "
            "o Data Warehouse Gold."
        ),
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


# ============================================================
# PIPELINE PRINCIPAL
# ============================================================

def main():
    args = get_arguments()

    total_start = time.perf_counter()

    print()
    print("=" * 70)
    print("E-COMMERCE COMPLAINT INTELLIGENCE PLATFORM")
    print("=" * 70)

    print(f"Período:       {args.period}")
    print(f"Origem Bronze: {args.source.upper()}")
    print(
        "Carga Gold:    "
        f"{'NÃO' if args.skip_gold else 'SIM'}"
    )

    print("=" * 70)

    completed_steps = []

    try:
        # ----------------------------------------------------
        # ETAPA 1 - INGESTÃO
        # ----------------------------------------------------

        if args.source == "local":
            ingest_local(args.period)
            completed_steps.append(
                "Ingestão local"
            )

        else:
            print()
            print(
                "[INFO] Modo MinIO selecionado. "
                "A consulta ao Consumidor.gov.br "
                "será dispensada."
            )

        # ----------------------------------------------------
        # ETAPA 2 - BRONZE -> SILVER
        # ----------------------------------------------------

        transform(
            args.period,
            args.source,
        )

        completed_steps.append(
            "Transformação Bronze -> Silver"
        )

        # ----------------------------------------------------
        # ETAPA 3 - SILVER -> STAGING
        # ----------------------------------------------------

        load_staging(
    args.period,
    args.source,
)

        completed_steps.append(
            "Carregamento PostgreSQL Staging"
        )

        # ----------------------------------------------------
        # ETAPA 4 - STAGING -> GOLD
        # ----------------------------------------------------

        if args.skip_gold:
            print()
            print(
                "[INFO] Carga Gold ignorada "
                "por solicitação (--skip-gold)."
            )

        else:
            load_gold()

            completed_steps.append(
                "Carregamento PostgreSQL Gold"
            )

    except subprocess.CalledProcessError as error:
        print()
        print("!" * 70)
        print("ERRO NA EXECUÇÃO DA PIPELINE")
        print("!" * 70)

        print(
            f"Comando que falhou: {error.cmd}"
        )
        print(
            f"Código de saída: {error.returncode}"
        )

        raise SystemExit(
            error.returncode
        ) from error

    except Exception as error:
        print()
        print("!" * 70)
        print("ERRO NA EXECUÇÃO DA PIPELINE")
        print("!" * 70)

        print(error)

        raise SystemExit(1) from error

    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    total_elapsed = (
        time.perf_counter() - total_start
    )

    print()
    print("=" * 70)
    print("PIPELINE FINALIZADA COM SUCESSO")
    print("=" * 70)

    print(f"Período: {args.period}")
    print(f"Origem:  {args.source.upper()}")

    print()
    print("Etapas concluídas:")

    for index, step in enumerate(
        completed_steps,
        start=1,
    ):
        print(
            f"  {index}. {step}"
        )

    print()
    print(
        f"Tempo total: {total_elapsed:.2f} segundos"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
