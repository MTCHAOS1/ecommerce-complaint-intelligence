
import argparse
import re
import zipfile

from pathlib import Path

import pandas as pd

from src.storage.download_from_minio import (
    download_from_minio,
)
from src.storage.minio_client import (
    get_minio_client,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SILVER_BUCKET = "ecommerce-silver"


# ============================================================
# ARGUMENTOS
# ============================================================

def get_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Transformação Bronze -> Silver "
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
        default="local",
        help="Origem do ZIP Bronze. Padrão: local.",
    )

    parser.add_argument(
        "--upload-silver",
        action="store_true",
        help="Envia o Parquet gerado para o MinIO Silver.",
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
# CAMINHOS
# ============================================================

def get_files(period, source):
    """
    Identifica o ZIP de entrada e o Parquet de saída.
    """

    csv_name = f"finalizadas_{period}.csv"

    if source == "local":
        zip_file = (
            RAW_DIR / f"finalizadas_{period}.zip"
        )

    elif source == "minio":
        zip_file = download_from_minio(
            "bronze",
            period,
        )

    else:
        raise ValueError(
            f"Origem inválida: {source}"
        )

    output_file = (
        PROCESSED_DIR / f"complaints_{period}.parquet"
    )

    return zip_file, csv_name, output_file


# ============================================================
# LEITURA BRONZE
# ============================================================

def load_raw(zip_file, csv_name):
    """
    Lê o CSV diretamente de dentro do ZIP.
    """

    if not zip_file.is_file():
        raise FileNotFoundError(
            f"Arquivo Bronze não encontrado: {zip_file}"
        )

    print(f"Lendo Bronze: {zip_file}")

    with zipfile.ZipFile(zip_file) as archive:

        files = archive.namelist()

        if csv_name not in files:
            raise FileNotFoundError(
                f"{csv_name} não encontrado dentro de "
                f"{zip_file}.\n"
                f"Arquivos encontrados: {files}"
            )

        with archive.open(csv_name) as csv_file:
            df = pd.read_csv(
                csv_file,
                sep=";",
                encoding="utf-8",
                low_memory=False,
            )

    print(f"Registros carregados: {len(df):,}")

    return df


# ============================================================
# TRANSFORMAÇÃO SILVER
# ============================================================

def transform(df):
    """
    Aplica as transformações da camada Silver.
    """

    column_mapping = {
        "Região": "regiao",
        "UF": "uf",
        "Cidade": "cidade",
        "Sexo": "sexo",
        "Faixa Etária": "faixa_etaria",
        "Data Finalização": "data_finalizacao",
        "Tempo Resposta": "tempo_resposta",
        "Nome Fantasia": "nome_fantasia",
        "Segmento de Mercado": "segmento_de_mercado",
        "Área": "area",
        "Assunto": "assunto",
        "Grupo Problema": "grupo_problema",
        "Problema": "problema",
        "Como Comprou Contratou": "como_comprou_contratou",
        "Procurou Empresa": "procurou_empresa",
        "Respondida": "respondida",
        "Situação": "situacao",
        "Avaliação Reclamação": "avaliacao_reclamacao",
        "Nota do Consumidor": "nota_do_consumidor",
    }

    df = df.rename(
        columns=column_mapping
    )

    expected_columns = list(
        column_mapping.values()
    )

    missing_columns = [
        column
        for column in expected_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Colunas esperadas não encontradas: "
            f"{missing_columns}"
        )

    df = df[
        expected_columns
    ].copy()

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    df["data_finalizacao"] = pd.to_datetime(
        df["data_finalizacao"],
        format="%Y-%m-%d",
        errors="coerce",
    )

    # --------------------------------------------------------
    # NUMÉRICOS
    # --------------------------------------------------------

    df["tempo_resposta"] = pd.to_numeric(
        df["tempo_resposta"],
        errors="coerce",
    )

    df["nota_do_consumidor"] = pd.to_numeric(
        df["nota_do_consumidor"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # BOOLEANOS
    # --------------------------------------------------------

    boolean_mapping = {
        "S": True,
        "N": False,
    }

    df["procurou_empresa"] = (
        df["procurou_empresa"]
        .map(boolean_mapping)
        .astype("boolean")
    )

    df["respondida"] = (
        df["respondida"]
        .map(boolean_mapping)
        .astype("boolean")
    )

    # --------------------------------------------------------
    # STRINGS
    # --------------------------------------------------------

    string_columns = [
        "regiao",
        "uf",
        "cidade",
        "sexo",
        "faixa_etaria",
        "nome_fantasia",
        "segmento_de_mercado",
        "area",
        "assunto",
        "grupo_problema",
        "problema",
        "como_comprou_contratou",
        "situacao",
        "avaliacao_reclamacao",
    ]

    for column in string_columns:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
        )

    return df


# ============================================================
# VALIDAÇÃO
# ============================================================

def validate_period(df, period):
    """Valida todas as datas antes de publicar a Silver."""
    from src.quality.period_validation import validate_period_dates
    validate_period_dates(df, period)
    print(f"[OK] Período validado: {period}")


# ============================================================
# PERSISTÊNCIA SILVER LOCAL
# ============================================================

def save_silver(df, output_file):
    """
    Persiste a camada Silver em Parquet.
    """

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_parquet(
        output_file,
        index=False,
    )

    print(
        f"[OK] Silver salva: {output_file}"
    )


# ============================================================
# UPLOAD SILVER MINIO
# ============================================================

def upload_silver(output_file, period):
    """
    Envia o Parquet para o MinIO Silver,
    mantendo o particionamento por ano e mês.
    """

    year, month = period.split("-")

    object_key = (
        f"consumidor_gov/"
        f"ano={year}/"
        f"mes={month}/"
        f"complaints_{period}.parquet"
    )

    client = get_minio_client()

    print()
    print("Enviando Silver para o MinIO...")

    client.upload_file(
        str(output_file),
        SILVER_BUCKET,
        object_key,
    )

    metadata = client.head_object(
        Bucket=SILVER_BUCKET,
        Key=object_key,
    )

    local_size = output_file.stat().st_size
    remote_size = metadata["ContentLength"]

    if local_size != remote_size:
        raise RuntimeError(
            "Tamanho divergente após upload da Silver. "
            f"Local: {local_size}. "
            f"MinIO: {remote_size}."
        )

    print(
        f"[OK] Silver armazenada: "
        f"s3://{SILVER_BUCKET}/{object_key}"
    )


# ============================================================
# PIPELINE DE TRANSFORMAÇÃO
# ============================================================

def main():
    args = get_arguments()

    print("=" * 60)
    print(f"TRANSFORMAÇÃO - {args.period}")
    print(f"Origem Bronze: {args.source}")
    print(
        "Upload Silver: "
        f"{'SIM' if args.upload_silver else 'NÃO'}"
    )
    print("=" * 60)

    zip_file, csv_name, output_file = get_files(
        args.period,
        args.source,
    )

    df = load_raw(
        zip_file,
        csv_name,
    )

    df = transform(df)

    validate_period(
        df,
        args.period,
    )

    save_silver(
        df,
        output_file,
    )

    if args.upload_silver:
        upload_silver(
            output_file,
            args.period,
        )

    print()
    print("=" * 60)
    print("TRANSFORMAÇÃO FINALIZADA COM SUCESSO")
    print("=" * 60)

    print(f"Registros: {len(df):,}")
    print(f"Colunas:   {len(df.columns)}")


if __name__ == "__main__":
    main()
