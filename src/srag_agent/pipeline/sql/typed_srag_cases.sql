-- Lê os CSVs da camada STAGING (data/staging), mantém só as colunas úteis, renomeia e tipa.
-- Sem regra de negócio: só leitura e tipagem (tabela temporária `typed_cases`, em memória).
-- Os campos usados apenas na chave (nº da notificação, município, sexo, idade etc.) viram um
-- hash irreversível e NÃO são persistidos.
SELECT
    COALESCE(
        TRY_CAST(SUBSTR(DT_NOTIFIC, 1, 10) AS DATE),
        CAST(TRY_STRPTIME(DT_NOTIFIC, '%d/%m/%Y') AS DATE)
    ) AS dt_notific,
    UPPER(TRIM(SG_UF_NOT)) AS uf,
    TRY_CAST(HOSPITAL AS TINYINT) AS hospital,
    TRY_CAST(UTI AS TINYINT) AS uti,
    TRY_CAST(EVOLUCAO AS TINYINT) AS evolucao,
    TRY_CAST(VACINA_COV AS TINYINT) AS vacina_cov,
    TRY_CAST(CLASSI_FIN AS TINYINT) AS classi_fin,
    sha256(concat_ws('|',
        NU_NOTIFIC, DT_NOTIFIC, SG_UF_NOT, CO_MUN_NOT, DT_SIN_PRI,
        CS_SEXO, NU_IDADE_N, TP_IDADE
    )) AS case_key
FROM read_csv(
    $files,
    delim = ';',
    header = true,
    all_varchar = true,
    encoding = 'utf-8',
    ignore_errors = true,
    union_by_name = true
)
