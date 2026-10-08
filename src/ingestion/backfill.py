
import argparse
import json
import logging
import time

from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import requests
from botocore.exceptions import ClientError
from sqlalchemy import text

from src.database.connection import get_engine
from src.ingestion.download_complaints import (
    get_publications,
    get_complaint_datasets,
)
from src.storage.minio_client import get_minio_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
LOG_DIR = PROJECT_ROOT / "logs"

CACHE_FILE = CACHE_DIR / "publications.json"

BASE_URL = "https://consumidor.gov.br"
BRONZE_BUCKET = "ecommerce-bronze"

for directory in (RAW_DIR, CACHE_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("backfill")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(
        LOG_DIR / "backfill.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file_handler)


# ============================================================
# PERÍODOS E CAMINHOS
# ============================================================

def get_periods(year, start_month, end_month):
    if not 1 <= start_month <= end_month <= 12:
        raise ValueError("Intervalo de meses inválido.")

    return [
        f"{year}-{month:02d}"
        for month in range(start_month, end_month + 1)
    ]


def local_zip_path(period):
    return RAW_DIR / f"finalizadas_{period}.zip"


def get_object_key(period):
    year, month = period.split("-")

    return (
        f"consumidor_gov/ano={year}/mes={month}/"
        f"finalizadas_{period}.zip"
    )


# ============================================================
# POSTGRESQL
# ============================================================

def register_periods(engine, periods):
    with engine.begin() as connection:
        for period in periods:
            connection.execute(
                text("""
                    INSERT INTO metadata.ingestion_control (
                        period, status
                    )
                    VALUES (:period, 'PENDING')
                    ON CONFLICT (period) DO NOTHING
                """),
                {"period": period},
            )


def mark_attempt(engine, period):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE metadata.ingestion_control
                SET attempts = attempts + 1,
                    last_attempt = NOW(),
                    error_message = NULL
                WHERE period = :period
            """),
            {"period": period},
        )


def mark_source_status(
    engine,
    period,
    source_status,
    message=None,
):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE metadata.ingestion_control
                SET source_status = :source_status,
                    source_checked_at = NOW(),
                    error_message = :message,
                    status = CASE
                        WHEN status = 'DOWNLOADED'
                        THEN status
                        ELSE 'PENDING'
                    END
                WHERE period = :period
            """),
            {
                "period": period,
                "source_status": source_status,
                "message": message,
            },
        )


def mark_success(engine, period, object_key):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE metadata.ingestion_control
                SET status = 'DOWNLOADED',
                    source_status = 'STORED',
                    downloaded_at = COALESCE(
                        downloaded_at, NOW()
                    ),
                    object_key = :object_key,
                    error_message = NULL
                WHERE period = :period
            """),
            {
                "period": period,
                "object_key": object_key,
            },
        )


def mark_failure(engine, period, error):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE metadata.ingestion_control
                SET status = 'FAILED',
                    error_message = :message
                WHERE period = :period
            """),
            {
                "period": period,
                "message": str(error)[:2000],
            },
        )


# ============================================================
# VALIDAÇÃO DE ZIP
# ============================================================

def validate_local_zip(path, period):
    if not path.is_file() or path.stat().st_size == 0:
        return False

    expected_name = f"finalizadas_{period}.csv"

    try:
        with ZipFile(path) as archive:
            members = [
                item
                for item in archive.infolist()
                if not item.is_dir()
            ]

            if not members:
                return False

            if archive.testzip() is not None:
                return False

            return any(
                Path(item.filename).name == expected_name
                and item.file_size > 0
                for item in members
            )

    except (BadZipFile, OSError):
        return False


# ============================================================
# MINIO
# ============================================================

def remote_object_exists(client, object_key):
    try:
        response = client.head_object(
            Bucket=BRONZE_BUCKET,
            Key=object_key,
        )

        return response["ContentLength"] > 0

    except ClientError as error:
        code = error.response.get(
            "Error", {}
        ).get("Code", "")

        if code in ("404", "NoSuchKey", "NotFound"):
            return False

        raise


def upload_bronze(client, path, object_key):
    expected_size = path.stat().st_size

    logger.info("Upload para MinIO: %s", path.name)

    client.upload_file(
        str(path),
        BRONZE_BUCKET,
        object_key,
    )

    response = client.head_object(
        Bucket=BRONZE_BUCKET,
        Key=object_key,
    )

    if response["ContentLength"] != expected_size:
        raise RuntimeError(
            f"Tamanho divergente no MinIO: {path.name}"
        )

    logger.info(
        "[OK] s3://%s/%s",
        BRONZE_BUCKET,
        object_key,
    )


# ============================================================
# CACHE DE PUBLICAÇÕES
# ============================================================

def save_cache(datasets):
    """
    Salva apenas metadados de publicações,
    nunca o conteúdo dos arquivos ZIP.
    """

    payload = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "datasets": datasets,
    }

    temporary = CACHE_FILE.with_suffix(".json.part")

    try:
        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(CACHE_FILE)

    finally:
        temporary.unlink(missing_ok=True)

    logger.info(
        "[OK] Cache atualizado: %s publicações",
        len(datasets),
    )


def load_cache():
    if not CACHE_FILE.is_file():
        logger.info("Nenhum cache disponível.")
        return {}

    try:
        payload = json.loads(
            CACHE_FILE.read_text(encoding="utf-8")
        )

        datasets = payload["datasets"]

        if not isinstance(datasets, dict):
            raise ValueError(
                "Formato inválido do cache."
            )

        logger.info(
            "Cache carregado. Atualizado em: %s",
            payload.get("updated_at", "desconhecido"),
        )

        return datasets

    except (OSError, ValueError, KeyError) as error:
        logger.warning(
            "Não foi possível carregar o cache: %s",
            error,
        )
        return {}


def normalize_datasets(datasets):
    """
    Converte a listagem em um dicionário
    indexado pelo nome do ZIP.

    O código de publicação precisa ser mantido
    para construir a URL de download.
    """

    normalized = {}

    for item in datasets:
        if not isinstance(item, dict):
            continue

        name = item.get("nomeArquivo")
        code = item.get("codigo")

        if not name or code is None:
            continue

        normalized[str(name)] = {
            "codigo": code,
            "nomeArquivo": str(name),
            "tamanhoArquivo": item.get(
                "tamanhoArquivo"
            ),
        }

    return normalized


def get_dataset_catalog():
    """
    Consulta a fonte e, se falhar,
    utiliza a última listagem válida.

    Retorna:
        datasets, origin, source_available
    """

    cached = load_cache()

    try:
        logger.info(
            "Consultando publicações do Consumidor.gov.br..."
        )

        publications = get_publications()
        datasets = get_complaint_datasets(publications)

        normalized = normalize_datasets(datasets)

        if not normalized:
            raise RuntimeError(
                "A consulta não retornou publicações "
                "com nome e código válidos."
            )

        # Preserva publicações já conhecidas,
        # caso a listagem atual seja parcial.
        merged = {**cached, **normalized}

        save_cache(merged)

        logger.info(
            "[OK] Consulta realizada com sucesso."
        )

        return merged, "API", True

    except Exception as error:
        logger.warning(
            "Falha na consulta ao Consumidor.gov.br: %s",
            error,
        )

        if cached:
            logger.warning(
                "Utilizando metadados do cache."
            )

            return cached, "CACHE", False

        logger.warning(
            "Sem cache disponível. "
            "Meses ausentes continuarão pendentes."
        )

        return {}, "UNAVAILABLE", False


# ============================================================
# DOWNLOAD
# ============================================================

def download_zip(dataset, period):
    destination = local_zip_path(period)
    temporary = destination.with_suffix(".zip.part")

    if validate_local_zip(destination, period):
        return destination

    code = dataset["codigo"]

    url = (
        f"{BASE_URL}/pages/publicacao/externo/"
        f"{code}/download"
    )

    logger.info(
        "Baixando %s...",
        destination.name,
    )

    try:
        with requests.get(
            url,
            stream=True,
            timeout=(15, 120),
        ) as response:
            response.raise_for_status()

            with temporary.open("wb") as output:
                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):
                    if chunk:
                        output.write(chunk)

        if not validate_local_zip(temporary, period):
            raise RuntimeError(
                f"ZIP inválido: {period}"
            )

        expected_size = dataset.get("tamanhoArquivo")

        if expected_size not in (None, ""):
            if temporary.stat().st_size != int(
                expected_size
            ):
                raise RuntimeError(
                    f"Tamanho divergente: {period}"
                )

        temporary.replace(destination)

        logger.info(
            "[OK] Download validado: %s",
            destination.name,
        )

        return destination

    finally:
        temporary.unlink(missing_ok=True)


# ============================================================
# IDENTIFICAÇÃO DOS MESES PENDENTES
# ============================================================

def check_existing_files(engine, client, periods):
    """
    Verifica primeiro o MinIO e os ZIPs locais.

    Só retorna períodos que realmente precisam
    consultar a fonte de dados.
    """

    pending = []
    results = {}

    for period in periods:
        object_key = get_object_key(period)

        logger.info(
            "Verificando Bronze: %s",
            period,
        )

        if remote_object_exists(client, object_key):
            mark_success(engine, period, object_key)

            logger.info(
                "[EXISTS] %s já está no MinIO.",
                period,
            )

            results[period] = "EXISTS"
            continue

        local_path = local_zip_path(period)

        if validate_local_zip(local_path, period):
            upload_bronze(
                client,
                local_path,
                object_key,
            )

            mark_success(
                engine,
                period,
                object_key,
            )

            logger.info(
                "[UPLOADED] %s enviado ao MinIO.",
                period,
            )

            results[period] = "UPLOADED"
            continue

        pending.append(period)

    return pending, results


# ============================================================
# PROCESSAMENTO DOS PENDENTES
# ============================================================

def process_pending_period(
    engine,
    client,
    period,
    datasets,
    origin,
    source_available,
):
    filename = f"finalizadas_{period}.zip"
    dataset = datasets.get(filename)

    if dataset is None:
        if source_available:
            source_status = "NOT_PUBLISHED"
            message = (
                "Período não encontrado na última "
                "consulta válida de publicações."
            )
        else:
            source_status = "SOURCE_UNAVAILABLE"
            message = (
                "Não foi possível verificar a "
                "disponibilidade do período."
            )

        mark_source_status(
            engine,
            period,
            source_status,
            message,
        )

        logger.info(
            "[PENDING] %s: %s",
            period,
            source_status,
        )

        return "PENDING"

    source_status = (
        "CACHED" if origin == "CACHE"
        else "AVAILABLE"
    )

    mark_source_status(
        engine,
        period,
        source_status,
    )

    mark_attempt(engine, period)

    try:
        local_path = download_zip(
            dataset,
            period,
        )

        object_key = get_object_key(period)

        upload_bronze(
            client,
            local_path,
            object_key,
        )

        mark_success(
            engine,
            period,
            object_key,
        )

        return "DOWNLOADED"

    except Exception as error:
        mark_failure(engine, period, error)

        logger.error(
            "[FAILED] %s: %s",
            period,
            error,
        )

        return "FAILED"


# ============================================================
# EXECUÇÃO DO BACKFILL
# ============================================================

def run_backfill(
    year,
    start_month,
    end_month,
    delay,
):
    periods = get_periods(
        year,
        start_month,
        end_month,
    )

    engine = get_engine()
    client = get_minio_client()

    register_periods(engine, periods)

    logger.info("=" * 70)
    logger.info(
        "BACKFILL: %s até %s",
        periods[0],
        periods[-1],
    )
    logger.info("=" * 70)

    # Primeiro tenta resolver tudo localmente.
    pending, results = check_existing_files(
        engine,
        client,
        periods,
    )

    if not pending:
        logger.info(
            "Todos os períodos já estão na Bronze. "
            "Consulta à API dispensada."
        )

    else:
        logger.info(
            "%s períodos precisam de coleta.",
            len(pending),
        )

        datasets, origin, source_available = (
            get_dataset_catalog()
        )

        download_attempts = 0

        for period in pending:
            filename = f"finalizadas_{period}.zip"

            # Aplica o intervalo apenas antes
            # de outra tentativa real de download.
            if (
                filename in datasets
                and download_attempts > 0
                and delay > 0
            ):
                time.sleep(delay)

            if filename in datasets:
                download_attempts += 1

            try:
                result = process_pending_period(
                    engine,
                    client,
                    period,
                    datasets,
                    origin,
                    source_available,
                )

            except Exception as error:
                logger.exception(
                    "Erro inesperado em %s",
                    period,
                )

                mark_failure(
                    engine,
                    period,
                    error,
                )

                result = "FAILED"

            results[period] = result

    logger.info("=" * 70)
    logger.info("RESUMO DO BACKFILL")

    for period in periods:
        logger.info(
            "%s: %s",
            period,
            results.get(period, "UNKNOWN"),
        )

    logger.info("=" * 70)

    completed = sum(
        result in (
            "EXISTS",
            "UPLOADED",
            "DOWNLOADED",
        )
        for result in results.values()
    )

    logger.info(
        "Concluídos: %s/%s",
        completed,
        len(periods),
    )

    return completed == len(periods)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Coleta histórica de reclamações "
            "do Consumidor.gov.br."
        )
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--start-month",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--end-month",
        type=int,
        default=12,
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
    )

    args = parser.parse_args()

    if not 2000 <= args.year <= 2100:
        parser.error("Ano inválido.")

    if args.delay < 0:
        parser.error(
            "O intervalo não pode ser negativo."
        )

    try:
        success = run_backfill(
            args.year,
            args.start_month,
            args.end_month,
            args.delay,
        )

    except Exception:
        logger.exception(
            "Falha geral do coletor."
        )
        raise SystemExit(1)

    if not success:
        logger.warning(
            "Coleta incompleta. "
            "Uma nova execução poderá retomar "
            "os períodos pendentes."
        )
        raise SystemExit(1)

    logger.info(
        "[OK] Backfill concluído com sucesso."
    )


if __name__ == "__main__":
    main()
