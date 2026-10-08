-- Reclamações por estado - Agosto de 2026

SELECT
    localidade.uf,
    COUNT(*) AS total_reclamacoes
FROM warehouse.fato_reclamacao AS fato
INNER JOIN warehouse.dim_localidade AS localidade
    ON localidade.localidade_id = fato.localidade_id
INNER JOIN warehouse.dim_tempo AS tempo
    ON tempo.data_id = fato.data_id
WHERE tempo.ano = 2026
  AND tempo.mes = 8
GROUP BY localidade.uf
ORDER BY total_reclamacoes DESC;