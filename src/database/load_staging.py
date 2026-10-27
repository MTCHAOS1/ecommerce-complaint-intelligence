
import argparse
import re
from pathlib import Path

from src.database.gold_lock import exclusive_operation

import pandas as pd
from sqlalchemy import text

from src.database.connection import get_engine
from src.storage.download_from_minio import download_from_minio


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DDL_FILE = (
    PROJECT_ROOT
    / "sql"
    / "staging"
    / "create_complaints.sql"
)

SCHEMA = "staging"
TABLE = "complaints"

CHUNK_SIZE = 5_000

EXPECTED_COLUMNS = [
    "regiao",
    "uf",
    "cidade",
    "sexo",
    "faixa_etaria",
    "data_finalizacao",
    "tempo_resposta",
    "nome_fantasia",
    "segmento_de_mercado",
    "area",
    "assunto",
    "grupo_problema",
    "problema",
    "como_comprou_contratou",
    "procurou_empresa",
    "respondida",
    "situacao",
    "avaliacao_reclamacao",
    "nota_do_consumidor",
]


# ============================================================
# ARGUMENTOS
# ============================================================

def get_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Carrega a camada Silver para o PostgreSQL "
            "Staging utilizando uma transação única."
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
        help="Origem da Silver. Padrão: local.",
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
# ARQUIVO SILVER
# ============================================================

def get_silver_file(period, source):
    """
    Obtém o Parquet da origem selecionada.
    """

    if source == "local":
        return (
            PROCESSED_DIR
            / f"complaints_{period}.parquet"
        )

    if source == "minio":
        return download_from_minio(
            "silver",
            period,
        )

    raise ValueError(
        f"Origem inválida: {source}"
    )


# ============================================================
# LEITURA DA SILVER
# ============================================================

def load_silver(silver_file, period):
    """
    Lê o Parquet e valida sua estrutura.
    """

    if not silver_file.is_file():
        raise FileNotFoundError(
            f"Silver não encontrada: {silver_file}"
        )

    print("=" * 60)
    print("LEITURA DA SILVER")
    print("=" * 60)

    print(f"\nPeríodo: {period}")
    print(f"Arquivo: {silver_file}")

    df = pd.read_parquet(
        silver_file
    )

    print(
        f"Registros encontrados: {len(df):,}"
    )

    print(
        f"Colunas encontradas: {len(df.columns)}"
    )

    missing_columns = [
        column
        for column in EXPECTED_COLUMNS
        if column not in df.columns
    ]

    unexpected_columns = [
        column
        for column in df.columns
        if column not in EXPECTED_COLUMNS
    ]

    if missing_columns or unexpected_columns:
        raise ValueError(
            "Estrutura inválida da Silver.\n"
            f"Colunas ausentes: {missing_columns}\n"
            f"Colunas inesperadas: {unexpected_columns}"
        )

    if df.empty:
        raise ValueError(
            "A Silver está vazia."
        )

    df = df[EXPECTED_COLUMNS].copy()

    print("[OK] Estrutura da Silver validada.")

    return df


# ============================================================
# VALIDAÇÃO DO PERÍODO
# ============================================================

def validate_period(df, period):
    """Aplica as mesmas regras de data da Silver e valida chaves dimensionais."""
    from src.quality.period_validation import validate_period_dates, validate_dimension_keys
    validate_period_dates(df, period)
    validate_dimension_keys(df)
    print(f"[OK] Período da Silver validado: {period}")
    print("[OK] Empresa, UF e cidade obrigatórias validadas.")


# ============================================================
# PREPARAÇÃO DA STAGING
# ============================================================

def create_staging_table(connection):
    """
    Recria a tabela utilizando a conexão da transação.
    """

    if not DDL_FILE.is_file():
        raise FileNotFoundError(
            f"DDL não encontrado: {DDL_FILE}"
        )

    ddl = DDL_FILE.read_text(
        encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print("PREPARAÇÃO DA STAGING")
    print("=" * 60)

    # Executa o DROP e o CREATE dentro da
    # transação que já está aberta.
    connection.exec_driver_sql(ddl)

    print(
        "\nTabela staging.complaints preparada "
        "dentro da transação."
    )


# ============================================================
# CARGA TRANSACIONAL
# ============================================================

def insert_data(df, connection):
    """
    Insere os registros usando a mesma conexão
    transacional para todos os lotes.
    """

    total_rows = len(df)

    print("\n" + "=" * 60)
    print("CARGA TRANSACIONAL DA STAGING")
    print("=" * 60)

    print(f"\nTotal: {total_rows:,}")
    print(f"Chunk: {CHUNK_SIZE:,}\n")

    for start in range(
        0,
        total_rows,
        CHUNK_SIZE,
    ):
        end = min(
            start + CHUNK_SIZE,
            total_rows,
        )

        chunk = df.iloc[start:end]

        # Importante:
        # con=connection mantém o to_sql
        # dentro da transação já aberta.
        chunk.to_sql(
            name=TABLE,
            con=connection,
            schema=SCHEMA,
            if_exists="append",
            index=False,
        )

        percentage = (
            end / total_rows
        ) * 100

        print(
            f"Carregados: "
            f"{end:,}/{total_rows:,} "
            f"({percentage:.1f}%)"
        )

    print(
        "\nTodos os lotes inseridos na transação."
    )


# ============================================================
# VALIDAÇÃO ANTES DO COMMIT
# ============================================================

def validate_load(df, connection, period):
    """
    Valida os registros dentro da transação,
    antes de confirmar a carga.
    """

    expected_rows = len(df)

    query = text(
        """
        SELECT
            COUNT(*) AS total,
            MIN(data_finalizacao) AS min_date,
            MAX(data_finalizacao) AS max_date
        FROM staging.complaints;
        """
    )

    result = connection.execute(
        query
    ).one()

    database_rows = result.total
    min_date = result.min_date
    max_date = result.max_date

    print("\n" + "=" * 60)
    print("VALIDAÇÃO ANTES DO COMMIT")
    print("=" * 60)

    print(f"\nPeríodo:    {period}")
    print(f"Silver:     {expected_rows:,}")
    print(f"PostgreSQL: {database_rows:,}")
    print(f"Data mínima: {min_date}")
    print(f"Data máxima: {max_date}")

    if expected_rows != database_rows:
        raise ValueError(
            "Quantidade de registros diferente "
            "entre Silver e PostgreSQL."
        )

    if min_date is None or max_date is None:
        raise ValueError(
            "A Staging não contém datas válidas."
        )

    expected_period = pd.Period(
        period,
        freq="M",
    )

    if (
        pd.Period(min_date, freq="M") != expected_period
        or pd.Period(max_date, freq="M") != expected_period
    ):
        raise ValueError(
            "O intervalo de datas da Staging "
            f"não pertence ao período {period}."
        )

    print(
        "\n[OK] Validação transacional concluída."
    )


# ============================================================
# PIPELINE
# ============================================================

@exclusive_operation
def run(period, source="local"):

    print("\n" + "=" * 60)
    print(f"SILVER -> STAGING | {period}")
    print(f"Origem Silver: {source.upper()}")
    print("Modo: TRANSACIONAL")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Obter e validar a Silver antes de alterar o banco.
    # --------------------------------------------------------

    silver_file = get_silver_file(
        period,
        source,
    )

    df = load_silver(
        silver_file,
        period,
    )

    validate_period(
        df,
        period,
    )

    from src.quality.validate_silver import validate_silver
    validate_silver(df, period)

    # --------------------------------------------------------
    # 2. Abrir uma única transação PostgreSQL.
    # --------------------------------------------------------

    engine = get_engine()

    try:
        with engine.begin() as connection:

            create_staging_table(
                connection
            )

            insert_data(
                df,
                connection
            )

            validate_load(
                df,
                connection,
                period,
            )

            # Ao sair normalmente do bloco,
            # SQLAlchemy executa COMMIT.
            #
            # Se qualquer etapa lançar uma exceção,
            # SQLAlchemy executa ROLLBACK.

        print()
        print("[OK] COMMIT realizado com sucesso.")

    except Exception:
        print()
        print(
            "[ERRO] Falha durante a carga. "
            "Transação revertida (ROLLBACK)."
        )
        raise

    finally:
        engine.dispose()

    print("\n" + "=" * 60)
    print("STAGING FINALIZADA COM SUCESSO")
    print("=" * 60)


def main():
    args = get_arguments()
    run(args.period, args.source)


if __name__ == "__main__":
    main()
