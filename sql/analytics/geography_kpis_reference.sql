-- Fórmula anterior de Geografia, preservada para conferência da otimização.
SELECT COUNT(*) AS reclamacoes,
       COUNT(DISTINCT l.uf) AS ufs,
       COUNT(DISTINCT (l.uf, BTRIM(l.cidade))) AS cidades
FROM warehouse.fato_reclamacao f
JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
JOIN warehouse.dim_localidade l ON l.localidade_id = f.localidade_id
WHERE t.ano = :ano AND t.mes = ANY(CAST(:meses AS INTEGER[]))
  AND (CAST(:uf AS TEXT) IS NULL OR l.uf = :uf)
