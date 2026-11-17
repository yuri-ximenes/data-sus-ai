-- TRATAMENTO (em memória): regras de qualidade e padronização sobre `stg_cases`.
-- Resultado na tabela temporária `int_cases`: uma linha por caso notificado válido.
-- Nada disso é gravado em disco; só os marts agregados são persistidos.
WITH valid_dates AS (
    -- Regra 1: data de notificação ausente, anterior a 2019 ou futura é inválida.
    SELECT * FROM stg_cases
    WHERE dt_notific BETWEEN DATE '2019-01-01' AND current_date
),

deduplicated AS (
    -- Regra 2: remove duplicatas (mesma chave pseudonimizada), preferindo a linha com desfecho.
    SELECT * EXCLUDE (row_num)
    FROM (
        SELECT
            *,
            row_number() OVER (
                PARTITION BY case_key
                ORDER BY CASE WHEN evolucao IN (1, 2, 3) THEN 0 ELSE 1 END
            ) AS row_num
        FROM valid_dates
    )
    WHERE row_num = 1
)

SELECT
    dt_notific,
    -- Regra 3: UF fora das 27 siglas vira NULL (o caso segue no total nacional).
    CASE WHEN list_contains($valid_ufs, uf) THEN uf END AS uf,
    -- Regra 4: quem passou por UTI necessariamente foi internado.
    -- Regra 5: código fora do domínio (ex.: 9 = ignorado) vira NULL.
    CASE
        WHEN uti = 1 THEN 1
        WHEN hospital IN (1, 2) THEN hospital
    END AS hospital,
    CASE WHEN uti IN (1, 2) THEN uti END AS uti,
    CASE WHEN evolucao IN (1, 2, 3) THEN evolucao END AS evolucao,
    CASE WHEN vacina_cov IN (1, 2) THEN vacina_cov END AS vacina_cov,
    -- 1 influenza, 2 outro vírus respiratório, 3 outro agente, 4 não especificado, 5 COVID-19.
    -- Casos recentes sem classificação final ficam NULL (não são imputados).
    CASE WHEN classi_fin IN (1, 2, 3, 4, 5) THEN classi_fin END AS classi_fin
FROM deduplicated
