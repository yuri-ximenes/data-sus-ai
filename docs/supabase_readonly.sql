-- Papel SOMENTE LEITURA para avaliadores do projeto.
-- Execute uma vez no SQL Editor do Supabase, como o usuário dono (postgres), DEPOIS da primeira
-- publicação dos marts (`uv run srag-report --publish-supabase`), que cria o schema `srag`.
-- Troque <SENHA_DO_LEITOR> por uma senha forte (ela será a senha publicada no README).

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'data_reader') THEN
        CREATE ROLE data_reader LOGIN PASSWORD '<SENHA_DO_LEITOR>';
    END IF;
END
$$;

-- Limites para uma credencial pública: poucas conexões, consultas curtas, nunca escreve.
ALTER ROLE data_reader CONNECTION LIMIT 5;
ALTER ROLE data_reader SET statement_timeout = '10s';
ALTER ROLE data_reader SET default_transaction_read_only = on;

GRANT USAGE ON SCHEMA srag TO data_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA srag TO data_reader;

-- As tabelas têm RLS ligado (a API pública do Supabase não lê nada); o leitor precisa de uma
-- política explícita de SELECT em cada uma.
DROP POLICY IF EXISTS data_reader_select ON srag.mart_daily_summary;
CREATE POLICY data_reader_select ON srag.mart_daily_summary
    FOR SELECT TO data_reader USING (true);

DROP POLICY IF EXISTS data_reader_select ON srag.mart_monthly_summary;
CREATE POLICY data_reader_select ON srag.mart_monthly_summary
    FOR SELECT TO data_reader USING (true);

DROP POLICY IF EXISTS data_reader_select ON srag.quality_report;
CREATE POLICY data_reader_select ON srag.quality_report
    FOR SELECT TO data_reader USING (true);
