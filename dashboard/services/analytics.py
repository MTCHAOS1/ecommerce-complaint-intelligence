"""Leitura analítica com cache e transação consistente para cada conjunto de gráficos."""
import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.database.connection import get_engine


BANCO_ESPERADO = "ecommerce_complaints"


@st.cache_data(ttl=600, show_spinner=False)
def consultar_lote(consultas: dict[str, str], parametros=None) -> dict[str, pd.DataFrame]:
    """Executa SELECTs no mesmo snapshot read-only e mantém o conjunto em cache."""
    for sql in consultas.values():
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise ValueError("A camada analítica aceita apenas consultas de leitura.")
    engine = get_engine()
    try:
        with engine.connect() as connection:
            banco = connection.execute(text("SELECT current_database()")).scalar_one()
            if banco != BANCO_ESPERADO:
                raise RuntimeError(f"Banco inesperado: {banco}")
            connection.rollback()
            with connection.begin():
                connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                return {
                    nome: pd.read_sql_query(text(sql), connection, params=parametros or {})
                    for nome, sql in consultas.items()
                }
    finally:
        engine.dispose()


def consultar(sql: str, parametros=None) -> pd.DataFrame:
    """Consulta avulsa com as mesmas restrições de leitura e cache."""
    return consultar_lote({"consulta": sql}, parametros)["consulta"]


def periodos_disponiveis() -> pd.DataFrame:
    """Períodos com fatos carregados; ausência não significa zero reclamações."""
    return consultar("""
        SELECT t.ano, t.mes, COUNT(*) AS total
        FROM warehouse.fato_reclamacao f
        JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
        GROUP BY t.ano, t.mes
        ORDER BY t.ano, t.mes
    """)
