"""Regressões: nenhuma data inválida pode ser publicada na Silver."""
from datetime import date
import pandas as pd
import pytest
from src.quality.period_validation import validate_period_dates, validate_dimension_keys
from src.transformation.transform_complaints import validate_period as validate_silver_period
from src.database.load_staging import validate_period as validate_staging_period


def sample(dates, names=None):
    n=len(dates)
    return pd.DataFrame({"data_finalizacao": dates, "nome_fantasia": names or ["Empresa"]*n,
                         "uf": ["MG"]*n, "cidade": ["Belo Horizonte"]*n})


@pytest.mark.parametrize("date_value", [None, "inválida", "2026-08-01"])
def test_silver_rejects_invalid_or_other_month(date_value):
    with pytest.raises(ValueError):
        validate_silver_period(sample(["2026-07-01", date_value]), "2026-07")


def test_staging_uses_same_date_validation():
    with pytest.raises(ValueError, match="datas"):
        validate_staging_period(sample(["2026-07-01", None]), "2026-07")


def test_staging_rejects_empty_company():
    with pytest.raises(ValueError, match="nome_fantasia"):
        validate_staging_period(sample(["2026-07-01"], ["  "]), "2026-07")


def test_valid_month_passes():
    validate_period_dates(sample([date(2026,7,1)]), "2026-07")
