import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from src.database.gold_audit import (
    count_gold_records,
    fail_gold_execution,
    finish_gold_execution,
    start_gold_execution,
)

PROJECT_ROOT = Path(__file__).resolve().parent
POSTGRES_HOST = "localhost"
POSTGRES_USER = "complaints_user"
POSTGRES_DATABASE = "ecommerce_complaints"
GOLD_SQL_FILE = PROJECT_ROOT / "sql" / "warehouse" / "load_star_schema.sql"


def run_command(command, step_name):
    print(f"\n{'=' * 70}\n{step_name}\n{'=' * 70}", flush=True)
    start = time.perf_counter()
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    elapsed = time.perf_counter() - start
    print(f"\n[OK] {step_name} concluída em {elapsed:.2f} segundos.")
    return elapsed


def ingest_local(period):
    return run_command(        [sys.executable, "-m", "src.ingestion.download_complaints", period],
        f"INGESTÃO LOCAL -> BRONZE | {period}",
    )


def transform(period, source):
    command = [
        sys.executable, "-m", "src.transformation.transform_complaints",
        period, "--source", source,
    ]
    if source == "minio":
        command.append("--upload-silver")
    return run_command(command, f"BRONZE -> SILVER | {period} | {source.upper()}")


def load_staging(period, source):
    return run_command(
        [sys.executable, "-m", "src.database.load_staging", period, "--source", source],
        f"SILVER -> POSTGRESQL STAGING | {period} | {source.upper()}",
    )


def load_gold(period):
    """Executa Gold e audita a tentativa em transações independentes."""
    if not GOLD_SQL_FILE.is_file():
        raise FileNotFoundError(f"Script Gold não encontrado: {GOLD_SQL_FILE}")

    execution_id, staging_count = start_gold_execution(period)
    print(f"[AUDITORIA] Execução {execution_id}: RUNNING | Staging: {staging_count:,}")
    command = [
        "psql", "-h", POSTGRES_HOST, "-U", POSTGRES_USER,
        "-d", POSTGRES_DATABASE, "-v", "ON_ERROR_STOP=1",
        "-f", str(GOLD_SQL_FILE),
    ]

    try:
        elapsed = run_command(command, "POSTGRESQL STAGING -> GOLD")
        gold_count = count_gold_records(period)
        if gold_count != staging_count:
            raise RuntimeError(
                f"Divergência após COMMIT: Staging={staging_count}, Gold={gold_count}"
            )
        finish_gold_execution(execution_id, gold_count)
        print(f"[AUDITORIA] Execução {execution_id}: SUCCESS | Gold: {gold_count:,}")
        return elapsed
    except Exception as error:
        try:
            fail_gold_execution(execution_id, error)
            print(f"[AUDITORIA] Execução {execution_id}: FAILED")
        except Exception as audit_error:
            print(f"[ERRO] Falha também ao registrar FAILED: {audit_error}", file=sys.stderr)
        raise


def get_arguments():
    parser = argparse.ArgumentParser(
        description="Pipeline de Engenharia de Dados do E-commerce Complaint Intelligence Platform."
    )
    parser.add_argument("period", help="Período no formato YYYY-MM.")
    parser.add_argument(
        "--source", choices=["local", "minio"], default="minio",
        help="Origem Bronze. Padrão: minio.",
    )
    parser.add_argument(
        "--skip-gold", action="store_true", help="Não carrega a Gold."
    )
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.period):
        parser.error("Período inválido. Utilize YYYY-MM.")
    return args


def main():
    args = get_arguments()
    start = time.perf_counter()
    print(f"\n{'=' * 70}")
    print("E-COMMERCE COMPLAINT INTELLIGENCE PLATFORM")
    print(f"{'=' * 70}")
    print(f"Período:       {args.period}")
    print(f"Origem Bronze: {args.source.upper()}")
    print(f"Carga Gold:    {'NÃO' if args.skip_gold else 'SIM'}")
    print(f"{'=' * 70}")
    completed = []
    try:
        if args.source == "local":
            ingest_local(args.period)
            completed.append("Ingestão local")
        else:
            print("\n[INFO] Modo MinIO selecionado. Consulta à API dispensada.")

        transform(args.period, args.source)
        completed.append("Transformação Bronze -> Silver")
        load_staging(args.period, args.source)
        completed.append("Carregamento PostgreSQL Staging")

        if args.skip_gold:
            print("\n[INFO] Carga Gold ignorada (--skip-gold).")
        else:
            load_gold(args.period)
            completed.append("Carregamento PostgreSQL Gold")

    except subprocess.CalledProcessError as error:
        print(f"\n[ERRO] Comando: {error.cmd} | Código: {error.returncode}", file=sys.stderr)
        raise SystemExit(error.returncode) from error
    except Exception as error:
        print(f"\n[ERRO] Pipeline interrompida: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    print(f"\n{'=' * 70}\nPIPELINE FINALIZADA COM SUCESSO")
    print(f"Período: {args.period} | Origem: {args.source.upper()}")
    print("Etapas concluídas:")
    for index, step in enumerate(completed, start=1):
        print(f"  {index}. {step}")
    print(f"Tempo total: {time.perf_counter() - start:.2f} segundos")
    print("=" * 70)


if __name__ == "__main__":
    main()
