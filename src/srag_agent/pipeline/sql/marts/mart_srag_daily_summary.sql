-- MART diário: contagens agregadas por data de notificação e UF (sem dados individuais).
-- Todas as métricas do relatório são somas destas colunas; as taxas são calculadas no código.
SELECT
    dt_notific AS dt,
    uf,
    count(*) AS cases,
    count(*) FILTER (WHERE hospital = 1 AND uti IS NOT NULL) AS icu_known,
    count(*) FILTER (WHERE hospital = 1 AND uti = 1) AS icu_admissions,
    count(*) FILTER (WHERE evolucao IS NOT NULL) AS outcome_known,
    count(*) FILTER (WHERE evolucao = 2) AS deaths,
    count(*) FILTER (WHERE vacina_cov IS NOT NULL) AS vaccination_known,
    count(*) FILTER (WHERE vacina_cov = 1) AS vaccinated,
    count(*) FILTER (WHERE classi_fin = 1) AS cases_influenza,
    count(*) FILTER (WHERE classi_fin = 2) AS cases_other_virus,
    count(*) FILTER (WHERE classi_fin = 3) AS cases_other_agent,
    count(*) FILTER (WHERE classi_fin = 4) AS cases_unspecified,
    count(*) FILTER (WHERE classi_fin = 5) AS cases_covid
FROM int_cases
GROUP BY dt_notific, uf
ORDER BY dt, uf
