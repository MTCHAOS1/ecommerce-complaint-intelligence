"""Definições dos indicadores e recorte único da visão geral."""

from dashboard.constants import MESES
from dashboard.services.analytics import consultar_lote
from dashboard.services.common import TEMPO_VALIDO, AREA, BASE, FILTRO, NOME_EMPRESA, parametros_periodo


CONSULTAS = {
    # Soma/contagem preservam médias ponderadas e nulos. O DISTINCT final opera
    # sobre grupos empresa/UF, reduzindo a ordenação de milhões de fatos.
    "indicadores": f"""
        WITH grupos AS (
            SELECT {NOME_EMPRESA} AS empresa, l.uf,
                   COUNT(*) AS reclamacoes,
                   SUM(f.tempo_resposta) FILTER (WHERE {TEMPO_VALIDO}) AS soma_tempo, COUNT(f.tempo_resposta) FILTER (WHERE {TEMPO_VALIDO}) AS base_tempo,
               COUNT(*) FILTER (WHERE f.tempo_resposta IS NOT NULL AND NOT ({TEMPO_VALIDO})) AS tempos_invalidos,
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
               COALESCE(SUM(tempos_invalidos), 0)::bigint AS tempos_invalidos,
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


def carregar_visao_geral(ano, meses):
    """KPIs e gráficos usam os mesmos parâmetros e o mesmo snapshot PostgreSQL."""
    return consultar_lote(CONSULTAS, parametros_periodo(ano, meses))
