"""Validação compartilhada de datas nas camadas Silver e Staging."""

import pandas as pd


def validate_period_dates(df, period):
    """Rejeita datas nulas, inválidas ou fora do mês solicitado."""
    if df.empty:
        raise ValueError("Dataset vazio: não é possível validar o período.")
    dates = pd.to_datetime(df["data_finalizacao"], errors="coerce")
    invalid_dates = int(dates.isna().sum())
    if invalid_dates:
        raise ValueError(
            f"Existem {invalid_dates:,} datas de finalização inválidas/nulas."
        )
    expected = pd.Period(period, freq="M")
    invalid_periods = int((dates.dt.to_period("M") != expected).sum())
    if invalid_periods:
        raise ValueError(
            f"Foram encontrados {invalid_periods:,} registros fora do período {period}."
        )


def validate_dimension_keys(df):
    """Falha cedo se chaves obrigatórias de empresa/localidade estiverem vazias."""
    for col in ("nome_fantasia", "uf", "cidade"):
        missing = df[col].isna() | df[col].astype("string").str.strip().eq("").fillna(False)
        count = int(missing.sum())
        if count:
            raise ValueError(f"{count:,} registros com {col} ausente/vazio.")
