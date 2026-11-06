"""Análise por nome fantasia normalizado, com recorte parametrizado."""

from dashboard.services.analytics import consultar_lote
from dashboard.services.common import TEMPO_VALIDO, BASE, FILTRO, NOME_EMPRESA, parametros_periodo

BASE_EMPRESA = BASE + ' JOIN warehouse.dim_empresa e ON e.empresa_id = f.empresa_id '
RECORTE = FILTRO + f' AND {NOME_EMPRESA} = :empresa'
CONSULTAS = {
    'indicadores': f"""
        SELECT COUNT(*) AS reclamacoes,
               ROUND(AVG(f.tempo_resposta) FILTER (WHERE {TEMPO_VALIDO}), 2) AS tempo_medio,
               COUNT(f.tempo_resposta) FILTER (WHERE {TEMPO_VALIDO}) AS base_tempo,
               COUNT(*) FILTER (WHERE f.tempo_resposta IS NOT NULL AND NOT ({TEMPO_VALIDO})) AS tempos_invalidos,
               ROUND(AVG(f.nota_do_consumidor), 2) AS nota_media,
               COUNT(f.nota_do_consumidor) AS base_nota
        {BASE_EMPRESA} WHERE {RECORTE}
    """,
    'mensal': f"""
        SELECT t.mes, COUNT(*) AS reclamacoes
        {BASE_EMPRESA} WHERE {RECORTE} GROUP BY t.mes ORDER BY t.mes
    """,
    'problemas': f"""
        SELECT COALESCE(NULLIF(BTRIM(c.problema), ''), 'Não informado') AS problema,
               COUNT(*) AS reclamacoes
        {BASE_EMPRESA}
        JOIN warehouse.dim_classificacao c ON c.classificacao_id = f.classificacao_id
        WHERE {RECORTE} GROUP BY 1 ORDER BY reclamacoes DESC, problema LIMIT 10
    """,
}


def listar_empresas(ano, meses):
    return consultar_lote({'empresas': f"""
        SELECT {NOME_EMPRESA} AS empresa, COUNT(*) AS reclamacoes
        {BASE_EMPRESA} WHERE {FILTRO}
        GROUP BY {NOME_EMPRESA} ORDER BY empresa
    """}, parametros_periodo(ano, meses))['empresas']


def carregar_empresa(ano, meses, empresa):
    parametros = parametros_periodo(ano, meses)
    if not isinstance(empresa, str) or not empresa.strip():
        raise ValueError('Selecione uma empresa.')
    parametros['empresa'] = empresa.strip()
    return consultar_lote(CONSULTAS, parametros)


def comparar_empresas(ano, meses, empresas):
    parametros = parametros_periodo(ano, meses)
    empresas = list(empresas)
    if not 1 <= len(empresas) <= 3 or any(
        not isinstance(empresa, str) or not empresa.strip() for empresa in empresas
    ):
        raise ValueError('Selecione de uma a três empresas.')
    parametros['empresas'] = sorted({e.strip() for e in empresas})
    return consultar_lote({'mensal': f"""
        WITH totais AS (
            SELECT t.mes, COUNT(*) AS total_mes {BASE}
            WHERE {FILTRO} GROUP BY t.mes
        ), selecionadas AS (
            SELECT t.mes, {NOME_EMPRESA} AS empresa, COUNT(*) AS reclamacoes
            {BASE_EMPRESA} WHERE {FILTRO}
              AND {NOME_EMPRESA} = ANY(CAST(:empresas AS TEXT[]))
            GROUP BY t.mes, {NOME_EMPRESA}
        )
        SELECT s.mes, s.empresa, s.reclamacoes, t.total_mes,
               ROUND(100.0 * s.reclamacoes / t.total_mes, 4) AS participacao
        FROM selecionadas s JOIN totais t USING (mes)
        ORDER BY s.mes, s.empresa
    """}, parametros)['mensal']
