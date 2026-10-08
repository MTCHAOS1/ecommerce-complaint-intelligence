from pathlib import Path

import pandas as pd


RAW_FILE = Path("data/raw/finalizadas_2026-08.zip")


def analyze_schema(file_path):
    df = pd.read_csv(
        file_path,
        sep=";",
        encoding="utf-8"
    )

    print("=" * 60)
    print("SCHEMA DO DATASET")
    print("=" * 60)

    print(f"\nLinhas: {len(df):,}")
    print(f"Colunas: {len(df.columns)}")

    print("\n" + "=" * 60)
    print("COLUNAS E TIPOS")
    print("=" * 60)

    for column in df.columns:
        print(
            f"{column:<30} "
            f"{str(df[column].dtype):<10}"
        )

    print("\n" + "=" * 60)
    print("VALORES ÚNICOS")
    print("=" * 60)

    for column in df.columns:

        unique_count = df[column].nunique(
            dropna=False
        )

        print(
            f"{column:<30} "
            f"{unique_count:,}"
        )

    # Colunas categóricas que queremos investigar
    categorical_columns = [
        "Região",
        "UF",
        "Sexo",
        "Faixa Etária",
        "Como Comprou Contratou",
        "Procurou Empresa",
        "Respondida",
        "Situação",
        "Avaliação Reclamação",
    ]

    print("\n" + "=" * 60)
    print("DOMÍNIOS DAS COLUNAS CATEGÓRICAS")
    print("=" * 60)

    for column in categorical_columns:

        if column not in df.columns:
            continue

        print(f"\n--- {column} ---")

        counts = df[column].value_counts(
            dropna=False
        )

        print(counts)


if __name__ == "__main__":

    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {RAW_FILE}"
        )

    analyze_schema(RAW_FILE)