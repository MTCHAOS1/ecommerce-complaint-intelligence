"""Consultas das páginas especializadas com recorte parametrizado e snapshot único."""

from dashboard.services.analytics import consultar_lote
from dashboard.services.common import BASE, FILTRO, AREA, parametros_periodo

UFS = tuple('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
LOCAL = BASE + ' JOIN warehouse.dim_localidade l ON l.localidade_id = f.localidade_id '
CLASSIFICACAO = BASE + ' JOIN warehouse.dim_classificacao c ON c.classificacao_id = f.classificacao_id '


def categoria(coluna):
    return f"COALESCE(NULLIF(BTRIM({coluna}), ''), 'Não informado')"


def distribuicao(base, filtro, expressao, nome, limite=''):
    return f"""
        SELECT {expressao} AS {nome}, COUNT(*) AS reclamacoes
        {base}
        WHERE {filtro}
        GROUP BY 1
        ORDER BY reclamacoes DESC, {nome} {limite}
    """


def carregar_geografia(ano, meses, uf=None):
    parametros = parametros_periodo(ano, meses)
    if uf is not None and uf not in UFS:
        raise ValueError('UF inválida.')
    parametros['uf'] = uf
    filtro = FILTRO + ' AND (CAST(:uf AS TEXT) IS NULL OR l.uf = :uf)'
    return consultar_lote({
        'indicadores': f"""
            SELECT COUNT(*) AS reclamacoes,
                   COUNT(DISTINCT l.uf) AS ufs,
                   COUNT(DISTINCT (l.uf, BTRIM(l.cidade))) AS cidades
            {LOCAL} WHERE {filtro}
        """,
        'estados': distribuicao(LOCAL, filtro, 'l.uf', 'uf'),
        'cidades': distribuicao(
            LOCAL, filtro, "BTRIM(l.cidade) || ' / ' || l.uf", 'cidade', 'LIMIT 15',
        ),
        'mensal': f"""
            SELECT t.mes, COUNT(*) AS reclamacoes
            {LOCAL} WHERE {filtro}
            GROUP BY t.mes ORDER BY t.mes
        """,
    }, parametros)


def listar_areas(ano, meses):
    consultas = {
        'areas': f"""
            SELECT DISTINCT {AREA} AS area
            {CLASSIFICACAO} WHERE {FILTRO} ORDER BY area
        """,
    }
    return consultar_lote(consultas, parametros_periodo(ano, meses))['areas']


def parametros_classificacao(ano, meses, area=None, assunto=None, grupo=None):
    parametros = parametros_periodo(ano, meses)
    for nome, valor in [('area', area), ('assunto', assunto), ('grupo', grupo)]:
        if valor is not None and (not isinstance(valor, str) or not valor.strip()):
            raise ValueError('Classificação inválida.')
        parametros[nome] = valor.strip() if valor is not None else None
    filtro = FILTRO
    for nome, coluna in [
        ('area', 'area'), ('assunto', 'assunto'), ('grupo', 'grupo_problema'),
    ]:
        filtro += (
            f' AND (CAST(:{nome} AS TEXT) IS NULL'
            f' OR {categoria("c." + coluna)} = :{nome})'
        )
    return parametros, filtro


def listar_assuntos(ano, meses, area=None):
    parametros, filtro = parametros_classificacao(ano, meses, area)
    consultas = {
        'assuntos': f"""
            SELECT DISTINCT {categoria("c.assunto")} AS assunto
            {CLASSIFICACAO} WHERE {filtro} ORDER BY assunto
        """,
    }
    return consultar_lote(consultas, parametros)['assuntos']


def listar_grupos(ano, meses, area=None, assunto=None):
    parametros, filtro = parametros_classificacao(ano, meses, area, assunto)
    consultas = {
        'grupos': f"""
            SELECT DISTINCT {categoria("c.grupo_problema")} AS grupo
            {CLASSIFICACAO} WHERE {filtro} ORDER BY grupo
        """,
    }
    return consultar_lote(consultas, parametros)['grupos']


def carregar_problemas(ano, meses, area=None, assunto=None, grupo=None, nivel=None):
    if nivel not in (None, 'areas', 'assuntos', 'grupos', 'problemas'):
        raise ValueError('Nível de ranking inválido.')
    parametros, filtro = parametros_classificacao(ano, meses, area, assunto, grupo)
    consultas = {
        'indicadores': f"""
            SELECT COUNT(*) AS reclamacoes, COUNT(DISTINCT {AREA}) AS areas
            {CLASSIFICACAO} WHERE {filtro}
        """,
    }
    for nome, coluna in [
        ('areas', 'area'), ('assuntos', 'assunto'),
        ('grupos', 'grupo_problema'), ('problemas', 'problema'),
    ]:
        if nivel is None or nome == nivel:
            consultas[nome] = distribuicao(
                CLASSIFICACAO, filtro, categoria('c.' + coluna), nome, 'LIMIT 15',
            )
    return consultar_lote(consultas, parametros)


METRICAS_ATENDIMENTO = """
    COUNT(*) AS reclamacoes,
    ROUND(AVG(f.tempo_resposta), 2) AS tempo_medio,
    COUNT(f.tempo_resposta) AS base_tempo,
    ROUND(AVG(f.nota_do_consumidor), 2) AS nota_media,
    COUNT(f.nota_do_consumidor) AS base_nota,
    COUNT(*) FILTER (WHERE f.respondida IS TRUE) AS respondidas,
    COUNT(f.respondida) AS base_respondida,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.respondida IS TRUE) / NULLIF(COUNT(f.respondida), 0), 2) AS percentual_respondidas
"""


def carregar_atendimento(ano, meses):
    return consultar_lote({
        'indicadores': f'SELECT {METRICAS_ATENDIMENTO} {BASE} WHERE {FILTRO}',
        'mensal': f"""
            SELECT t.mes, {METRICAS_ATENDIMENTO}
            {BASE} WHERE {FILTRO}
            GROUP BY t.mes ORDER BY t.mes
        """,
        'avaliacoes': distribuicao(BASE, FILTRO, categoria('f.avaliacao_reclamacao'), 'avaliacao'),
        'notas': f"""
            SELECT f.nota_do_consumidor AS nota, COUNT(*) AS reclamacoes
            {BASE} WHERE {FILTRO} AND f.nota_do_consumidor IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """,
    }, parametros_periodo(ano, meses))
