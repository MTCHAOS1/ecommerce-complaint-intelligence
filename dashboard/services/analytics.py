import pandas as pd
import streamlit as st

from sqlalchemy import text
from src.database.connection import get_engine


BANCO_ESPERADO = "ecommerce_complaints"


@st.cache_data(ttl=600)
def consultar(sql: str, parametros=None) -> pd.DataFrame:
    """
    Executa consultas analíticas de leitura no PostgreSQL.
    Armazena os resultados em cache por 10 minutos.
    """

    instrucao = sql.lstrip().upper()

    if not instrucao.startswith("SELECT") and not instrucao.startswith("WITH"):
        raise ValueError(
            "A camada analítica aceita apenas consultas de leitura."
        )

    engine = get_engine()

    try:
        with engine.connect() as conn:
            banco = conn.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if banco != BANCO_ESPERADO:
                raise RuntimeError(
                    f"Banco inesperado: {banco}"
                )

            conn.rollback()

            with conn.begin():
                conn.execute(
                    text("SET TRANSACTION READ ONLY")
                )

                resultado = pd.read_sql_query(
                    text(sql),
                    conn,
                    params=parametros or {},
                )

            return resultado

    finally:
        engine.dispose()


@st.cache_data(ttl=600)
def periodos_disponiveis() -> pd.DataFrame:
    """
    Retorna os períodos efetivamente carregados na Gold.
    """

    return consultar("""
        SELECT
            t.ano,
            t.mes,
            COUNT(*) AS total
        FROM warehouse.fato_reclamacao f
        JOIN warehouse.dim_tempo t
            ON t.data_id = f.data_id
        GROUP BY t.ano, t.mes
        ORDER BY t.ano, t.mes
    """)
