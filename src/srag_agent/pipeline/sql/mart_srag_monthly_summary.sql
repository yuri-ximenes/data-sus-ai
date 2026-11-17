-- MART mensal: derivado do mart diário, para o gráfico dos últimos 12 meses.
SELECT
    CAST(date_trunc('month', dt) AS DATE) AS month,
    uf,
    sum(cases) AS cases
FROM read_parquet($input)
GROUP BY 1, uf
ORDER BY month, uf
