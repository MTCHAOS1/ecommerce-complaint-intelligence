from src.database.gold_lock import exclusive_operation
from src.database.connection import secret

import os
from pathlib import Path

import boto3
from botocore.client import Config
from dotenv import load_dotenv
from src.storage.artifacts import publish_versioned


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def get_minio_client():
    """
    Cria um cliente S3 conectado ao MinIO.
    """

    access_key = secret('MINIO_ACCESS_KEY')
    secret_key = secret('MINIO_SECRET_KEY')
    if access_key is None and secret_key is None:
        # Compatibilidade local; instalações novas devem usar a conta restrita.
        access_key = os.getenv('MINIO_ROOT_USER')
        secret_key = os.getenv('MINIO_ROOT_PASSWORD')

    if not access_key or not secret_key:
        raise RuntimeError(
            "Configure MINIO_ACCESS_KEY e MINIO_SECRET_KEY juntos."
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

    publish_versioned(client, local_path, bucket_name, object_name)

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
