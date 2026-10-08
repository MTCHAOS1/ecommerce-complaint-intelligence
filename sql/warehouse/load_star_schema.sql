-- Executar via psql com -v ON_ERROR_STOP=1.
-- A Staging deve conter exatamente um mes validado.
BEGIN;

-- ============================================================
-- 0. VALIDACAO PREVIA DA STAGING
-- ============================================================
DO $$
DECLARE
    v_total BIGINT;
    v_periodos INTEGER;
    v_datas_nulas BIGINT;
BEGIN
    SELECT COUNT(*),
           COUNT(DISTINCT DATE_TRUNC('month', data_finalizacao)),
           COUNT(*) FILTER (WHERE data_finalizacao IS NULL)
    INTO v_total, v_periodos, v_datas_nulas
    FROM staging.complaints;

    IF v_total = 0 OR v_periodos <> 1 OR v_datas_nulas > 0 THEN
        RAISE EXCEPTION
            'Staging invalida: total=%, periodos=%, datas_nulas=%',
            v_total, v_periodos, v_datas_nulas;
    END IF;
END $$;

-- ============================================================
-- 1. DIMENSAO EMPRESA
-- ============================================================
INSERT INTO warehouse.dim_empresa (nome_fantasia, segmento_de_mercado)
SELECT DISTINCT nome_fantasia, segmento_de_mercado
FROM staging.complaints
WHERE nome_fantasia IS NOT NULL
ON CONFLICT DO NOTHING;

-- ============================================================
-- 2. DIMENSAO LOCALIDADE
-- ============================================================
INSERT INTO warehouse.dim_localidade (regiao, uf, cidade)
SELECT DISTINCT ON (uf, cidade) regiao, uf, cidade
FROM staging.complaints
WHERE uf IS NOT NULL AND cidade IS NOT NULL
ORDER BY uf, cidade, regiao
ON CONFLICT DO NOTHING;

-- ============================================================
-- 3. DIMENSAO TEMPO
-- ============================================================
INSERT INTO warehouse.dim_tempo (
    data_id, data, dia, mes, nome_mes, trimestre, ano
)
SELECT DISTINCT
    TO_CHAR(data_finalizacao, 'YYYYMMDD')::INTEGER,
    data_finalizacao,
    EXTRACT(DAY FROM data_finalizacao)::SMALLINT,
    EXTRACT(MONTH FROM data_finalizacao)::SMALLINT,
    CASE EXTRACT(MONTH FROM data_finalizacao)::INTEGER
        WHEN 1 THEN 'Janeiro'
        WHEN 2 THEN 'Fevereiro'
        WHEN 3 THEN 'Marco'
        WHEN 4 THEN 'Abril'
        WHEN 5 THEN 'Maio'
        WHEN 6 THEN 'Junho'
        WHEN 7 THEN 'Julho'
        WHEN 8 THEN 'Agosto'
        WHEN 9 THEN 'Setembro'
        WHEN 10 THEN 'Outubro'
        WHEN 11 THEN 'Novembro'
        WHEN 12 THEN 'Dezembro'
    END,
    EXTRACT(QUARTER FROM data_finalizacao)::SMALLINT,
    EXTRACT(YEAR FROM data_finalizacao)::SMALLINT
FROM staging.complaints
WHERE data_finalizacao IS NOT NULL
ON CONFLICT DO NOTHING;

-- ============================================================
-- 4. DIMENSAO CLASSIFICACAO
-- ============================================================
INSERT INTO warehouse.dim_classificacao (area, assunto, grupo_problema, problema)
SELECT DISTINCT area, assunto, grupo_problema, problema
FROM staging.complaints
ON CONFLICT DO NOTHING;

-- ============================================================
-- 5. SUBSTITUICAO DO MES INTEIRO NA FATO
-- ============================================================
DO $$
DECLARE
    v_periodo DATE;
    v_removidos BIGINT;
BEGIN
    SELECT DATE_TRUNC('month', MIN(data_finalizacao))::DATE
    INTO v_periodo
    FROM staging.complaints;

    DELETE FROM warehouse.fato_reclamacao AS fato
    USING warehouse.dim_tempo AS tempo
    WHERE fato.data_id = tempo.data_id
      AND tempo.data >= v_periodo
      AND tempo.data < (v_periodo + INTERVAL '1 month');

    GET DIAGNOSTICS v_removidos = ROW_COUNT;
    RAISE NOTICE 'Periodo %: % registros anteriores removidos.',
        TO_CHAR(v_periodo, 'YYYY-MM'), v_removidos;
END $$;

-- ============================================================
-- 6. CARGA DA TABELA FATO
-- ============================================================
INSERT INTO warehouse.fato_reclamacao (
    empresa_id, localidade_id, data_id, classificacao_id,
    sexo, faixa_etaria, tempo_resposta, como_comprou_contratou,
    procurou_empresa, respondida, situacao, avaliacao_reclamacao,
    nota_do_consumidor
)
SELECT
    empresa.empresa_id,
    localidade.localidade_id,
    tempo.data_id,
    classificacao.classificacao_id,
    staging.sexo,
    staging.faixa_etaria,
    staging.tempo_resposta,
    staging.como_comprou_contratou,
    staging.procurou_empresa,
    staging.respondida,
    staging.situacao,
    staging.avaliacao_reclamacao,
    staging.nota_do_consumidor
FROM staging.complaints AS staging
INNER JOIN warehouse.dim_empresa AS empresa
    ON empresa.nome_fantasia = staging.nome_fantasia
   AND empresa.segmento_de_mercado IS NOT DISTINCT FROM staging.segmento_de_mercado
INNER JOIN warehouse.dim_localidade AS localidade
    ON localidade.uf = staging.uf
   AND localidade.cidade = staging.cidade
INNER JOIN warehouse.dim_tempo AS tempo
    ON tempo.data = staging.data_finalizacao
INNER JOIN warehouse.dim_classificacao AS classificacao
    ON classificacao.area IS NOT DISTINCT FROM staging.area
   AND classificacao.assunto IS NOT DISTINCT FROM staging.assunto
   AND classificacao.grupo_problema IS NOT DISTINCT FROM staging.grupo_problema
   AND classificacao.problema IS NOT DISTINCT FROM staging.problema;

-- ============================================================
-- 7. VALIDACAO DA GOLD ANTES DO COMMIT
-- ============================================================
DO $$
DECLARE
    v_periodo DATE;
    v_staging BIGINT;
    v_gold BIGINT;
BEGIN
    SELECT DATE_TRUNC('month', MIN(data_finalizacao))::DATE, COUNT(*)
    INTO v_periodo, v_staging
    FROM staging.complaints;

    SELECT COUNT(*) INTO v_gold
    FROM warehouse.fato_reclamacao AS fato
    INNER JOIN warehouse.dim_tempo AS tempo
        ON tempo.data_id = fato.data_id
    WHERE tempo.data >= v_periodo
      AND tempo.data < (v_periodo + INTERVAL '1 month');

    IF v_staging <> v_gold THEN
        RAISE EXCEPTION 'Divergencia Gold: Staging=%, Gold=%',
            v_staging, v_gold;
    END IF;

    RAISE NOTICE 'Gold validada: % registros no periodo %.',
        v_gold, TO_CHAR(v_periodo, 'YYYY-MM');
END $$;

COMMIT;
