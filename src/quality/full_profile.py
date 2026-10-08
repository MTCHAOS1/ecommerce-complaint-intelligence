from pathlib import Path

import pandas as pd


RAW_FILE = Path("data/raw/finalizadas_2026-08.zip")

CHUNK_SIZE = 50_000


def profile_dataset(file_path):
    total_rows = 0
    null_counts = None
    duplicate_rows = 0

    print("Iniciando profiling completo...")
    print(f"Arquivo: {file_path}")
    print(f"Chunk size: {CHUNK_SIZE:,}")
    print()

    chunks = pd.read_csv(
        file_path,
        sep=";",
        encoding="utf-8",
        chunksize=CHUNK_SIZE
    )

    for chunk_number, chunk in enumerate(chunks, start=1):

        rows = len(chunk)
        total_rows += rows

        # Contagem de valores nulos
        chunk_nulls = chunk.isnull().sum()

        if null_counts is None:
            null_counts = chunk_nulls
        else:
            null_counts = null_counts.add(
                chunk_nulls,
                fill_value=0
            )

        # Duplicatas dentro do chunk
        duplicate_rows += chunk.duplicated().sum()

        print(
            f"Chunk {chunk_number}: "
            f"{rows:,} linhas processadas"
        )

    print("\n" + "=" * 50)
    print("RESULTADO DO PROFILING")
    print("=" * 50)

    print(f"\nTotal de registros: {total_rows:,}")

    print("\nTotal de colunas:")
    print(len(null_counts))

    print("\nValores nulos por coluna:")

    for column, count in null_counts.items():

        percentage = (
            count / total_rows
        ) * 100

        print(
            f"{column}: "
            f"{int(count):,} "
            f"({percentage:.2f}%)"
        )

    print(
        f"\nDuplicatas encontradas nos chunks: "
        f"{duplicate_rows:,}"
    )


if __name__ == "__main__":

    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {RAW_FILE}"
        )

    profile_dataset(RAW_FILE)