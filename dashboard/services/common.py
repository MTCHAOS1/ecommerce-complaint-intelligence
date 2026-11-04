"""Recorte e expressões SQL compartilhados pelos serviços analíticos."""

from numbers import Integral

from dashboard.constants import MESES


NOME_EMPRESA = "BTRIM(e.nome_fantasia)"
AREA = "COALESCE(NULLIF(BTRIM(c.area), ''), 'Não informado')"
FILTRO = "t.ano = :ano AND t.mes = ANY(CAST(:meses AS INTEGER[]))"
BASE = """
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
"""


def parametros_periodo(ano, meses):
    """Normaliza o recorte e rejeita seleção vazia antes de consultar o banco."""
    if isinstance(ano, bool) or not isinstance(ano, Integral) or not 1 <= ano <= 9999:
        raise ValueError("Ano inválido.")
    meses = list(meses)
    if not meses:
        raise ValueError("Selecione pelo menos um mês.")
    if any(
        isinstance(mes, bool) or not isinstance(mes, Integral) or mes not in MESES
        for mes in meses
    ):
        raise ValueError("Meses inválidos.")
    return {"ano": int(ano), "meses": sorted({int(mes) for mes in meses})}
