from pathlib import Path
from zipfile import ZipFile

import pandas as pd


RAW_FILE = Path("data/raw/finalizadas_2026-08.zip")


def inspect_zip(zip_path):
    """Mostra os arquivos existentes dentro do ZIP."""

    with ZipFile(zip_path, "r") as zip_file:
        files = zip_file.namelist()

    print("Arquivos encontrados no ZIP:")

    for file in files:
        print(f" - {file}")

    return files


def load_sample(zip_path, rows=1000):
    """
    Carrega apenas uma amostra do dataset.

    Isso evita carregar todo o CSV na memória durante
    nossa primeira inspeção.
    """

    dataframe = pd.read_csv(
        zip_path,
        nrows=rows,
        sep=";",
        encoding="utf-8"
    )

    return dataframe


def profile_dataframe(dataframe):
    """Executa uma inspeção inicial do dataset."""

    print("\n==============================")
    print("DIMENSÕES DA AMOSTRA")
    print("==============================")

    print(f"Linhas: {dataframe.shape[0]}")
    print(f"Colunas: {dataframe.shape[1]}")

    print("\n==============================")
    print("COLUNAS")
    print("==============================")

    for column in dataframe.columns:
        print(column)

    print("\n==============================")
    print("TIPOS")
    print("==============================")

    print(dataframe.dtypes)

    print("\n==============================")
    print("VALORES NULOS")
    print("==============================")

    print(dataframe.isnull().sum())

    print("\n==============================")
    print("PRIMEIROS REGISTROS")
    print("==============================")

    print(dataframe.head())


if __name__ == "__main__":

    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {RAW_FILE}"
        )

    inspect_zip(RAW_FILE)

    df = load_sample(
        RAW_FILE,
        rows=1000
    )

    profile_dataframe(df)