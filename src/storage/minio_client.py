from src.database.gold_lock import exclusive_operation

import os
from pathlib import Path

import boto3
from botocore.client import Config
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def get_minio_client():
    """
    Cria um cliente S3 conectado ao MinIO.
    """

    access_key = os.getenv("MINIO_ROOT_USER")
    secret_key = os.getenv("MINIO_ROOT_PASSWORD")

    if not access_key or not secret_key:
        raise RuntimeError(
            "Credenciais do MinIO não configuradas no .env"
        )

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:9000"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


@exclusive_operation
def upload_file(local_path, bucket_name, object_name=None):
    """
    Envia um arquivo local para um bucket MinIO.
    """

    local_path = Path(local_path)

    if not local_path.is_file():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {local_path}"
        )

    if object_name is None:
        object_name = local_path.name

    client = get_minio_client()

    print(f"Enviando: {local_path}")
    print(f"Bucket: {bucket_name}")
    print(f"Objeto: {object_name}")

    client.upload_file(
        str(local_path),
        bucket_name,
        object_name,
    )

    print("[OK] Upload concluído.")


def list_objects(bucket_name):
    """
    Lista os objetos armazenados em um bucket.
    """

    client = get_minio_client()

    response = client.list_objects_v2(
        Bucket=bucket_name
    )

    objects = response.get("Contents", [])

    for obj in objects:
        print(
            f"{obj['Key']} - {obj['Size']} bytes"
        )

    return objects