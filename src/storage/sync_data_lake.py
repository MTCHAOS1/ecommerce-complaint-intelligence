from src.database.gold_lock import exclusive_operation

import argparse
import re
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from src.storage.minio_client import get_minio_client, upload_file


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BUCKETS = {
    "bronze": "ecommerce-bronze",
    "silver": "ecommerce-silver",
}


# ============================================================
# VALIDAÇÃO DO PERÍODO
# ============================================================

def validate_period(period):
    """
    Valida o formato YYYY-MM.
    """

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ValueError(
            f"Período inválido: {period}. "
            "Utilize o formato YYYY-MM."
        )

    return period


# ============================================================
# LOCALIZAÇÃO DOS ARQUIVOS
# ============================================================

def get_local_file(layer, period):
    """
    Retorna o caminho do arquivo local conforme a camada.
    """

    if layer == "bronze":
        return (
            PROJECT_ROOT
            / "data"
            / "raw"
            / f"finalizadas_{period}.zip"
        )

    if layer == "silver":
        return (
            PROJECT_ROOT
            / "data"
            / "processed"
            / f"complaints_{period}.parquet"
        )

    raise ValueError(
        f"Camada inválida: {layer}"
    )


# ============================================================
# CAMINHO DO OBJETO NO MINIO
# ============================================================

def get_object_name(local_file, period):
    """
    Organiza os objetos por fonte, ano e mês.
    """

    year, month = period.split("-")

    return (
        f"consumidor_gov/"
        f"ano={year}/"
        f"mes={month}/"
        f"{local_file.name}"
    )


# ============================================================
# VALIDAÇÃO DO ARQUIVO LOCAL
# ============================================================

def validate_local_file(local_file):
    """
    Verifica se o arquivo existe e não está vazio.
    """

    if not local_file.is_file():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {local_file}"
        )

    file_size = local_file.stat().st_size

    if file_size == 0:
        raise ValueError(
            f"Arquivo vazio: {local_file}"
        )

    print(f"[OK] Arquivo local validado: {file_size:,} bytes")

    return file_size


# ============================================================
# VALIDAÇÃO DO OBJETO NO MINIO
# ============================================================

def validate_remote_object(bucket_name, object_name, expected_size):
    """
    Confirma que o objeto existe no MinIO e possui
    o mesmo tamanho do arquivo local.
    """

    client = get_minio_client()

    response = client.head_object(
        Bucket=bucket_name,
        Key=object_name,
    )

    remote_size = response["ContentLength"]

    if remote_size != expected_size:
        raise RuntimeError(
            "Tamanho divergente após upload. "
            f"Local: {expected_size} bytes. "
            f"MinIO: {remote_size} bytes."
        )

    print(f"[OK] Objeto remoto validado: {remote_size:,} bytes")


# ============================================================
# SINCRONIZAÇÃO COM MINIO
# ============================================================

@exclusive_operation
def sync_layer(layer, period):
    """
    Sincroniza um arquivo local com o bucket correspondente.

    Bronze:
        data/raw/finalizadas_YYYY-MM.zip

    Silver:
        data/processed/complaints_YYYY-MM.parquet
    """

    layer = layer.lower()
    period = validate_period(period)

    if layer not in BUCKETS:
        raise ValueError(
            f"Camada inválida: {layer}. "
            "Utilize bronze ou silver."
        )

    local_file = get_local_file(layer, period)
    bucket_name = BUCKETS[layer]
    object_name = get_object_name(local_file, period)

    print()
    print("=" * 70)
    print(f"SINCRONIZAÇÃO {layer.upper()} -> MINIO")
    print("=" * 70)

    print(f"Período: {period}")
    print(f"Arquivo local: {local_file}")
    print(f"Bucket: {bucket_name}")
    print(f"Objeto: {object_name}")

    # --------------------------------------------------------
    # ETAPA 1 - VALIDAR ARQUIVO LOCAL
    # --------------------------------------------------------

    file_size = validate_local_file(local_file)

    # --------------------------------------------------------
    # ETAPA 2 - REALIZAR UPLOAD
    # --------------------------------------------------------

    print()
    print("Iniciando upload...")

    upload_file(
        local_path=local_file,
        bucket_name=bucket_name,
        object_name=object_name,
    )

    # --------------------------------------------------------
    # ETAPA 3 - VALIDAR OBJETO REMOTO
    # --------------------------------------------------------

    print()
    print("Validando objeto no MinIO...")

    validate_remote_object(
        bucket_name=bucket_name,
        object_name=object_name,
        expected_size=file_size,
    )

    print()
    print(f"[OK] Camada {layer.upper()} sincronizada com sucesso.")
    print(f"Destino: s3://{bucket_name}/{object_name}")

    return object_name


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Sincroniza arquivos das camadas Bronze e Silver "
            "com o Data Lake MinIO."
        )
    )

    parser.add_argument(
        "layer",
        choices=["bronze", "silver"],
        help="Camada do Data Lake",
    )

    parser.add_argument(
        "period",
        help="Período no formato YYYY-MM",
    )

    args = parser.parse_args()

    try:
        sync_layer(
            layer=args.layer,
            period=args.period,
        )

    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
        ClientError,
        BotoCoreError,
    ) as error:

        print()
        print("!" * 70)
        print("ERRO NA SINCRONIZAÇÃO COM O MINIO")
        print("!" * 70)

        print(error)

        raise SystemExit(1) from error


if __name__ == "__main__":
    main()