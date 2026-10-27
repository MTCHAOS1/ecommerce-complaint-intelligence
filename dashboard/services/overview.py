"""Definições dos indicadores e recorte único da visão geral."""
from numbers import Integral

from dashboard.services.analytics import consultar_lote


MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}
NOME_EMPRESA = "BTRIM(e.nome_fantasia)"
AREA = "COALESCE(NULLIF(BTRIM(c.area), ''), 'Não informado')"
FILTRO = "t.ano = :ano AND t.mes = ANY(CAST(:meses AS INTEGER[]))"
BASE = """
    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
"""
CONSULTAS = {
    # Soma/contagem preservam médias ponderadas e nulos. O DISTINCT final opera
    # sobre grupos empresa/UF, reduzindo a ordenação de milhões de fatos.
    "indicadores": f"""
        WITH grupos AS (
            SELECT {NOME_EMPRESA} AS empresa, l.uf,
                   COUNT(*) AS reclamacoes,
                   SUM(f.tempo_resposta) AS soma_tempo, COUNT(f.tempo_resposta) AS base_tempo,
                   SUM(f.nota_do_consumidor) AS soma_nota, COUNT(f.nota_do_consumidor) AS base_nota
            {BASE}
            JOIN warehouse.dim_empresa e ON e.empresa_id = f.empresa_id
            JOIN warehouse.dim_localidade l ON l.localidade_id = f.localidade_id
            WHERE {FILTRO}
            GROUP BY {NOME_EMPRESA}, l.uf
        )
        SELECT COALESCE(SUM(reclamacoes), 0)::bigint AS reclamacoes,
               COUNT(DISTINCT empresa) AS empresas, COUNT(DISTINCT uf) AS ufs,
               ROUND(SUM(soma_tempo) / NULLIF(SUM(base_tempo), 0), 2) AS tempo_medio,
               COALESCE(SUM(base_tempo), 0)::bigint AS base_tempo,
               ROUND(SUM(soma_nota) / NULLIF(SUM(base_nota), 0), 2) AS nota_media,
               COALESCE(SUM(base_nota), 0)::bigint AS base_nota
        FROM grupos
    """,
    "mensal": f"""
        SELECT t.mes, COUNT(*) AS reclamacoes
        {BASE} WHERE {FILTRO}
        GROUP BY t.mes ORDER BY t.mes
    """,
    "empresas": f"""
        SELECT {NOME_EMPRESA} AS empresa, COUNT(*) AS reclamacoes
        {BASE}
        JOIN warehouse.dim_empresa e ON e.empresa_id = f.empresa_id
        WHERE {FILTRO}
        GROUP BY {NOME_EMPRESA}
        ORDER BY reclamacoes DESC, {NOME_EMPRESA}
        LIMIT 15
    """,
    "estados": f"""
        SELECT l.uf, COUNT(*) AS reclamacoes
        {BASE}
        JOIN warehouse.dim_localidade l ON l.localidade_id = f.localidade_id
        WHERE {FILTRO}
        GROUP BY l.uf ORDER BY reclamacoes DESC, l.uf
    """,
    "areas": f"""
        SELECT {AREA} AS area, COUNT(*) AS reclamacoes
        {BASE}
        JOIN warehouse.dim_classificacao c ON c.classificacao_id = f.classificacao_id
        WHERE {FILTRO}
        GROUP BY {AREA}
        ORDER BY reclamacoes DESC, area LIMIT 15
    """,
}


def parametros_periodo(ano, meses):
    """Normaliza o recorte e rejeita seleção vazia antes de consultar o banco."""
    if isinstance(ano, bool) or not isinstance(ano, Integral) or not 1 <= ano <= 9999:
        raise ValueError("Ano inválido.")
    meses = list(meses)
    if not meses:
        raise ValueError("Selecione pelo menos um mês.")
    if any(isinstance(mes, bool) or not isinstance(mes, Integral) or mes not in MESES for mes in meses):
        raise ValueError("Meses inválidos.")
    return {"ano": int(ano), "meses": sorted({int(mes) for mes in meses})}


def carregar_visao_geral(ano, meses):
    """KPIs e gráficos usam os mesmos parâmetros e o mesmo snapshot PostgreSQL."""
    return consultar_lote(CONSULTAS, parametros_periodo(ano, meses))
