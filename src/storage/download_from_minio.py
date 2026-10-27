from src.database.gold_lock import exclusive_operation


import argparse
from pathlib import Path

from botocore.exceptions import ClientError

from src.storage.minio_client import get_minio_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BRONZE_BUCKET = "ecommerce-bronze"
SILVER_BUCKET = "ecommerce-silver"

CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "minio"


def get_object_info(layer, period):
    year, month = period.split("-")

    if layer == "bronze":
        bucket = BRONZE_BUCKET
        filename = f"finalizadas_{period}.zip"

    elif layer == "silver":
        bucket = SILVER_BUCKET
        filename = f"complaints_{period}.parquet"

    else:
        raise ValueError(
            "Camada inválida. Utilize bronze ou silver."
        )

    object_key = (
        f"consumidor_gov/ano={year}/mes={month}/{filename}"
    )

    return bucket, object_key, filename


@exclusive_operation
def download_from_minio(layer, period):
    bucket, object_key, filename = get_object_info(
        layer,
        period,
    )

    destination_dir = CACHE_DIR / layer
    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = destination_dir / filename
    temporary = destination.with_name(
        destination.name + ".part"
    )

    client = get_minio_client()

    print("=" * 70)
    print(f"DOWNLOAD MINIO - {layer.upper()}")
    print("=" * 70)

    print(f"Bucket: {bucket}")
    print(f"Objeto: {object_key}")
    print(f"Destino: {destination}")

    try:
        metadata = client.head_object(
            Bucket=bucket,
            Key=object_key,
        )

        expected_size = metadata["ContentLength"]

        if expected_size <= 0:
            raise RuntimeError(
                "O objeto remoto está vazio."
            )

        # Nesta primeira versão, sempre atualizamos
        # o cache a partir do objeto remoto.
        client.download_file(
            bucket,
            object_key,
            str(temporary),
        )

        actual_size = temporary.stat().st_size

        if actual_size != expected_size:
            raise RuntimeError(
                "Tamanho divergente após download. "
                f"Esperado: {expected_size}. "
                f"Obtido: {actual_size}."
            )

        temporary.replace(destination)

        print()
        print("[OK] Arquivo recuperado do MinIO.")
        print(f"Tamanho: {actual_size:,} bytes")

        return destination

    except ClientError as error:
        code = error.response.get(
            "Error", {}
        ).get("Code", "")

        if code in ("404", "NoSuchKey", "NotFound"):
            raise FileNotFoundError(
                f"Objeto não encontrado: "
                f"s3://{bucket}/{object_key}"
            ) from error

        raise

    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Recupera arquivos Bronze ou Silver "
            "do Data Lake MinIO."
        )
    )

    parser.add_argument(
        "layer",
        choices=["bronze", "silver"],
    )

    parser.add_argument(
        "period",
        help="Período no formato YYYY-MM",
    )

    args = parser.parse_args()

    download_from_minio(
        args.layer,
        args.period,
    )


if __name__ == "__main__":
    main()
