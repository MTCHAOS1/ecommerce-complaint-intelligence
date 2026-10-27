-- Referência sem agregação intermediária, preservada para conferência e benchmark.
-- Não é usada na renderização do dashboard.
SELECT COUNT(*) AS reclamacoes,
               COUNT(DISTINCT BTRIM(e.nome_fantasia)) AS empresas,
               COUNT(DISTINCT l.uf) AS ufs,
               ROUND(AVG(f.tempo_resposta), 2) AS tempo_medio,
               COUNT(f.tempo_resposta) AS base_tempo,
               ROUND(AVG(f.nota_do_consumidor), 2) AS nota_media,
               COUNT(f.nota_do_consumidor) AS base_nota

    FROM warehouse.fato_reclamacao f
    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id

        JOIN warehouse.dim_empresa e ON e.empresa_id = f.empresa_id
        JOIN warehouse.dim_localidade l ON l.localidade_id = f.localidade_id
        WHERE t.ano = :ano AND t.mes = ANY(CAST(:meses AS INTEGER[]))
