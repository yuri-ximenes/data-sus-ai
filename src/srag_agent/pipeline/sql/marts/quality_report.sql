-- Relatório de qualidade: compara os dados tipados (antes) e tratados (depois). Só contagens.
WITH s AS (SELECT * FROM stg_cases),
     c AS (SELECT * FROM int_cases)
SELECT
    (SELECT count(*) FROM s) AS linhas_staging,
    (SELECT count(*) FROM s
        WHERE dt_notific IS NULL
           OR dt_notific < DATE '2019-01-01'
           OR dt_notific > current_date) AS descartadas_data_invalida,
    (SELECT count(*) FROM c) AS linhas_tratadas,
    (SELECT count(*) FROM s WHERE uf IS NOT NULL AND NOT list_contains($valid_ufs, uf))
        AS uf_invalida_para_nula,
    (SELECT count(*) FROM s
        WHERE uti = 1 AND COALESCE(hospital, 0) <> 1
          AND dt_notific BETWEEN DATE '2019-01-01' AND current_date) AS hospital_inferido_por_uti,
    (SELECT count(*) FROM s WHERE hospital NOT IN (1, 2)) AS hospital_ignorado_para_nulo,
    (SELECT count(*) FROM s WHERE uti NOT IN (1, 2)) AS uti_ignorado_para_nulo,
    (SELECT count(*) FROM s WHERE evolucao NOT IN (1, 2, 3)) AS evolucao_ignorada_para_nulo,
    (SELECT count(*) FROM s WHERE vacina_cov NOT IN (1, 2)) AS vacina_ignorada_para_nulo,
    (SELECT count(*) FROM s WHERE classi_fin NOT IN (1, 2, 3, 4, 5)) AS classi_fin_ignorada_para_nulo,
    (SELECT count(*) FROM c WHERE uf IS NULL) AS ausentes_uf,
    (SELECT count(*) FROM c WHERE classi_fin IS NULL) AS ausentes_classi_fin,
    (SELECT count(*) FROM c WHERE uti IS NULL) AS ausentes_uti,
    (SELECT count(*) FROM c WHERE evolucao IS NULL) AS ausentes_evolucao,
    (SELECT count(*) FROM c WHERE vacina_cov IS NULL) AS ausentes_vacina_cov
