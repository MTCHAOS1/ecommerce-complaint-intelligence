"""Regras compartilhadas executadas antes de publicar/carregar Silver."""
import pandas as pd
import pytest

from src.quality.validate_silver import EXPECTED_COLUMNS, validate_silver


def valid_frame():
    row = dict.fromkeys(EXPECTED_COLUMNS)
    row.update(data_finalizacao=pd.Timestamp('2026-07-01'), nome_fantasia='Empresa',
               uf='SP', cidade='São Paulo', procurou_empresa=True, respondida=False,
               avaliacao_reclamacao='Resolvida', nota_do_consumidor=4)
    return pd.DataFrame([row])


def test_valid_quality():
    validate_silver(valid_frame(), '2026-07')


@pytest.mark.parametrize('column,value', [
    ('uf', 'XX'), ('cidade', ' '), ('nome_fantasia', None),
    ('respondida', 'S'), ('nota_do_consumidor', 6),
    ('nota_do_consumidor', None), ('avaliacao_reclamacao', 'Não Avaliada'),
    ('data_finalizacao', pd.Timestamp('2026-08-01')),
])
def test_reject_invalid_quality(column, value):
    frame = valid_frame()
    frame[column] = value
    with pytest.raises(ValueError):
        validate_silver(frame, '2026-07')
