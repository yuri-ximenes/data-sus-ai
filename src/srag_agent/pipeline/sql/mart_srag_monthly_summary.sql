-- MART mensal: derivado do mart diário, para o gráfico dos últimos 12 meses.
SELECT
    CAST(date_trunc('month', dt) AS DATE) AS month,
    uf,
    CAST(sum(cases) AS BIGINT) AS cases
FROM daily_mart
GROUP BY 1, uf
ORDER BY month, uf
