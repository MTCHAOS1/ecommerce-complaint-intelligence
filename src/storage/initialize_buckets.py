"""Cria somente os buckets ausentes, sem alterar objetos ou permissões."""

from botocore.exceptions import ClientError

from src.storage.download_from_minio import BRONZE_BUCKET, SILVER_BUCKET
from src.storage.minio_client import get_minio_client


def initialize_buckets(client):
    """Retorna os nomes dos buckets criados; outros erros são propagados."""
    created = []
    for bucket in (BRONZE_BUCKET, SILVER_BUCKET):
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise
            client.create_bucket(Bucket=bucket)
            created.append(bucket)
    return created


def main():
    created = initialize_buckets(get_minio_client())
    print("Buckets criados: " + (", ".join(created) if created else "nenhum"))
    print(f"[OK] Buckets disponíveis: {BRONZE_BUCKET}, {SILVER_BUCKET}")


if __name__ == "__main__":
    main()
