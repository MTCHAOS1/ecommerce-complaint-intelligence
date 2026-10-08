from pathlib import Path

import pandas as pd


SILVER_FILE = Path(
    "data/processed/complaints_2026-08.parquet"
)

VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO"
}

EXPECTED_COLUMNS = {
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
}


def load_silver():
    """Carrega o arquivo Silver."""

    if not SILVER_FILE.exists():
        raise FileNotFoundError(
            f"Silver não encontrada: {SILVER_FILE}"
        )

    return pd.read_parquet(SILVER_FILE)


def validate_columns(df):
    """Verifica se o schema esperado está presente."""

    current_columns = set(df.columns)

    missing = EXPECTED_COLUMNS - current_columns
    unexpected = current_columns - EXPECTED_COLUMNS

    if missing:
        raise ValueError(
            f"Colunas ausentes: {sorted(missing)}"
        )

    if unexpected:
        raise ValueError(
            f"Colunas inesperadas: {sorted(unexpected)}"
        )

    print("[OK] Schema com 19 colunas esperado.")


def validate_empty_dataset(df):
    """Impede que uma Silver vazia seja considerada válida."""

    if df.empty:
        raise ValueError("Dataset Silver está vazio.")

    print(f"[OK] Dataset possui {len(df):,} registros.")


def validate_uf(df):
    """Valida as siglas das unidades federativas."""

    invalid_ufs = set(
        df["uf"].dropna().unique()
    ) - VALID_UFS

    if invalid_ufs:
        raise ValueError(
            f"UFs inválidas encontradas: {invalid_ufs}"
        )

    print("[OK] UFs válidas.")


def validate_boolean_columns(df):
    """Valida as colunas booleanas."""

    columns = [
        "procurou_empresa",
        "respondida"
    ]

    for column in columns:

        invalid = df[
            df[column].notna()
            & ~df[column].isin([True, False])
        ]

        if not invalid.empty:
            raise ValueError(
                f"Valores inválidos em {column}."
            )

    print("[OK] Colunas booleanas válidas.")


def validate_dates(df):
    """Verifica datas inválidas/nulas após transformação."""

    invalid_dates = df[
        "data_finalizacao"
    ].isna().sum()

    if invalid_dates > 0:
        raise ValueError(
            f"Datas inválidas encontradas: {invalid_dates:,}"
        )

    print("[OK] Datas de finalização válidas.")


def validate_consumer_score(df):
    """
    Verifica se notas preenchidas estão no intervalo
    permitido de 1 a 5.
    """

    scores = df[
        "nota_do_consumidor"
    ].dropna()

    invalid_scores = scores[
        ~scores.between(1, 5)
    ]

    if not invalid_scores.empty:
        raise ValueError(
            "Notas fora do intervalo 1-5 encontradas."
        )

    print("[OK] Notas do consumidor entre 1 e 5.")


def validate_not_evaluated_score(df):
    """
    Reclamações não avaliadas não devem possuir
    nota do consumidor.
    """

    invalid = df[
        (df["avaliacao_reclamacao"] == "Não Avaliada")
        & (df["nota_do_consumidor"].notna())
    ]

    if not invalid.empty:
        raise ValueError(
            f"{len(invalid):,} reclamações não avaliadas "
            "possuem nota."
        )

    print(
        "[OK] Reclamações não avaliadas "
        "não possuem nota."
    )


def validate_evaluated_score(df):
    """
    Reclamações avaliadas como Resolvida ou
    Não Resolvida devem possuir nota.
    """

    evaluated = df[
        "avaliacao_reclamacao"
    ].isin(
        ["Resolvida", "Não Resolvida"]
    )

    invalid = df[
        evaluated
        & df["nota_do_consumidor"].isna()
    ]

    if not invalid.empty:
        raise ValueError(
            f"{len(invalid):,} reclamações avaliadas "
            "estão sem nota."
        )

    print(
        "[OK] Reclamações avaliadas possuem nota."
    )


def validate_silver(df):
    """Executa todas as regras de Data Quality."""

    print("=" * 60)
    print("DATA QUALITY - SILVER")
    print("=" * 60)

    validate_empty_dataset(df)
    validate_columns(df)
    validate_uf(df)
    validate_boolean_columns(df)
    validate_dates(df)
    validate_consumer_score(df)
    validate_not_evaluated_score(df)
    validate_evaluated_score(df)

    print("\n" + "=" * 60)
    print("SILVER APROVADA")
    print("=" * 60)


if __name__ == "__main__":

    dataframe = load_silver()

    validate_silver(dataframe)