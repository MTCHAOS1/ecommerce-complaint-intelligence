from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_engine


st.set_page_config(
    page_title="E-commerce Complaint Intelligence",
    page_icon="📊",
    layout="wide",
)

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",
    4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro",
    10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


@st.cache_data(ttl=600)
def consultar(sql, parametros=None):
    engine = get_engine()
    try:
        with engine.connect() as conn:
            banco = conn.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if banco != "ecommerce_complaints":
                raise RuntimeError(
                    f"Banco inesperado: {banco}"
                )

            return pd.read_sql_query(
                text(sql),
                conn,
                params=parametros or {},
            )
    finally:
        engine.dispose()


@st.cache_data(ttl=600)
def periodos_disponiveis():
    return consultar("""
        SELECT t.ano, t.mes, COUNT(*) AS total
        FROM warehouse.fato_reclamacao f
        JOIN warehouse.dim_tempo t
            ON t.data_id = f.data_id
        GROUP BY t.ano, t.mes
        ORDER BY t.ano, t.mes
    """)


def filtro_sql():
    return """
        t.ano = :ano
        AND t.mes = ANY(CAST(:meses AS INTEGER[]))
    """


st.title("E-commerce Complaint Intelligence")
st.caption(
    "Análise de reclamações públicas do Consumidor.gov.br "
    "a partir do Data Warehouse PostgreSQL."
)

try:
    periodos = periodos_disponiveis()
except Exception as erro:
    st.error(f"Não foi possível consultar o banco: {erro}")
    st.stop()

if periodos.empty:
    st.warning("Nenhum período foi carregado na Gold.")
    st.stop()

anos = sorted(
    periodos["ano"].astype(int).unique().tolist(),
    reverse=True,
)

with st.sidebar:
    st.header("Filtros")

    ano = st.selectbox("Ano", anos)

    disponiveis = sorted(
        periodos.loc[
            periodos["ano"] == ano, "mes"
        ].astype(int).tolist()
    )

    meses = st.multiselect(
        "Meses",
        options=list(MESES.keys()),
        default=disponiveis,
        format_func=lambda mes: MESES[mes],
    )

    st.caption("Os indicadores consideram os meses selecionados.")

if not meses:
    st.info("Selecione pelo menos um mês.")
    st.stop()

parametros = {"ano": int(ano), "meses": meses}

# Indicadores gerais
indicadores = consultar(f"""
    SELECT
        COUNT(*) AS reclamacoes,
        COUNT(DISTINCT f.empresa_id) AS empresas,
        COUNT(DISTINCT l.uf) AS estados,
        ROUND(AVG(f.tempo_resposta), 2) AS tempo_medio,
        ROUND(AVG(f.nota_do_consumidor), 2) AS nota_media
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
    JOIN warehouse.dim_localidade l
        ON l.localidade_id = f.localidade_id
    WHERE {filtro_sql()}
""", parametros).iloc[0]

st.subheader("Visão geral")

col1, col2, col3 = st.columns(3)

col1.metric(
    "Reclamações",
    f"{int(indicadores['reclamacoes']):,}".replace(",", "."),
)
col2.metric(
    "Empresas",
    f"{int(indicadores['empresas']):,}".replace(",", "."),
)
col3.metric(
    "Estados (UF)",
    int(indicadores["estados"]),
)

col4, col5 = st.columns(2)

tempo = indicadores["tempo_medio"]
nota = indicadores["nota_media"]

col4.metric(
    "Tempo médio de resposta",
    f"{float(tempo):.2f}" if pd.notna(tempo) else "N/D",
)
col5.metric(
    "Nota média do consumidor",
    f"{float(nota):.2f}" if pd.notna(nota) else "N/D",
)

st.caption(
    "O tempo médio é exibido na unidade registrada na fonte; "
    "não foi presumida uma unidade de medida."
)

st.divider()

# Evolução mensal do ano inteiro
mensal = periodos.loc[periodos["ano"] == ano].copy()

serie = pd.DataFrame({"mes": list(range(1, 13))})
mensal = serie.merge(mensal, on="mes", how="left")
mensal["nome_mes"] = mensal["mes"].map(MESES)
mensal["status"] = mensal["total"].apply(
    lambda valor: "Sem dados carregados"
    if pd.isna(valor) else "Carregado"
)

st.subheader("Evolução mensal")

fig_mensal = px.bar(
    mensal,
    x="nome_mes",
    y="total",
    color="status",
    category_orders={"nome_mes": list(MESES.values())},
    labels={
        "nome_mes": "Mês",
        "total": "Reclamações",
        "status": "Situação",
    },
)

st.plotly_chart(fig_mensal, width="stretch")

ausentes = mensal.loc[
    mensal["total"].isna(), "nome_mes"
].tolist()

if ausentes:
    st.info(
        "Meses sem dados carregados: " + ", ".join(ausentes)
        + ". Eles não representam zero reclamações."
    )

# Ranking de empresas
empresas = consultar(f"""
    SELECT
        e.nome_fantasia AS empresa,
        COUNT(*) AS reclamacoes
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
    JOIN warehouse.dim_empresa e
        ON e.empresa_id = f.empresa_id
    WHERE {filtro_sql()}
    GROUP BY e.nome_fantasia
    ORDER BY reclamacoes DESC
    LIMIT 15
""", parametros)

# Distribuição geográfica
estados = consultar(f"""
    SELECT
        l.uf,
        COUNT(*) AS reclamacoes
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
    JOIN warehouse.dim_localidade l
        ON l.localidade_id = f.localidade_id
    WHERE {filtro_sql()}
    GROUP BY l.uf
    ORDER BY reclamacoes DESC
""", parametros)

col_esq, col_dir = st.columns(2)

with col_esq:
    st.subheader("Empresas mais reclamadas")
    fig = px.bar(
        empresas.sort_values("reclamacoes"),
        x="reclamacoes",
        y="empresa",
        orientation="h",
        labels={
            "empresa": "Empresa",
            "reclamacoes": "Reclamações",
        },
    )
    st.plotly_chart(fig, width="stretch")

with col_dir:
    st.subheader("Reclamações por UF")
    fig = px.bar(
        estados,
        x="uf",
        y="reclamacoes",
        labels={
            "uf": "Estado",
            "reclamacoes": "Reclamações",
        },
    )
    st.plotly_chart(fig, width="stretch")

# Principais áreas
areas = consultar(f"""
    SELECT
        COALESCE(c.area, 'Não informado') AS area,
        COUNT(*) AS reclamacoes
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
    JOIN warehouse.dim_classificacao c
        ON c.classificacao_id = f.classificacao_id
    WHERE {filtro_sql()}
    GROUP BY c.area
    ORDER BY reclamacoes DESC
    LIMIT 15
""", parametros)

st.subheader("Principais áreas de reclamação")

fig_areas = px.bar(
    areas.sort_values("reclamacoes"),
    x="reclamacoes",
    y="area",
    orientation="h",
    labels={
        "area": "Área",
        "reclamacoes": "Reclamações",
    },
)

st.plotly_chart(fig_areas, width="stretch")

st.divider()
st.caption(
    "Fonte: Consumidor.gov.br | "
    "Camada Gold: ecommerce_complaints | "
    "Consultas somente leitura | Cache: 10 minutos"
)
