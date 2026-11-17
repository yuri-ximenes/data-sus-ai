"""Teste de integração: staging (CSV) -> tratamento -> marts em memória, com CSV sintético."""

import duckdb
import pytest

from srag_agent.audit import AuditLogger
from srag_agent.config import Settings
from srag_agent.pipeline import build_marts
from srag_agent.pipeline.runner import clean_cases, load_staging, quality_report
from srag_agent.pipeline.sensitive import assert_no_sensitive_columns

HEADER = (
    "NU_NOTIFIC;DT_NOTIFIC;SG_UF_NOT;CO_MUN_NOT;DT_SIN_PRI;CS_SEXO;NU_IDADE_N;TP_IDADE;"
    "HOSPITAL;UTI;EVOLUCAO;VACINA_COV;NU_CPF;CLASSI_FIN"
)
ROWS = [
    # 1 e 2: mesma notificação (duplicata); deve sobrar a que tem desfecho conhecido.
    "1;2026-11-01T00:00:00.000Z;SP;355030;2026-10-30;M;30;3;1;1;9;1;12345678901;5",
    "1;2026-11-01T00:00:00.000Z;SP;355030;2026-10-30;M;30;3;1;1;2;1;12345678901;5",
    # 3: HOSPITAL ignorado (9) mas passou por UTI -> internação inferida; vacina 9 -> nulo.
    "2;02/11/2026;RJ;330455;2026-11-01;F;5;3;9;1;1;9;12345678902;1",
    # 4 e 5: datas inválidas (texto e anterior a 2019) devem ser descartadas.
    "3;abc;SP;355030;2026-11-01;F;40;3;1;2;1;1;12345678903;4",
    "4;2018-01-01T00:00:00.000Z;SP;355030;2018-01-01;F;40;3;1;2;1;1;12345678904;4",
    # 6: UF inválida e classificação ignorada (9) viram nulo; o caso segue no total nacional.
    "5;2026-11-03T00:00:00.000Z;XX;355030;2026-11-02;M;50;3;1;2;2;2;12345678905;9",
]
MART_COLUMNS = {
    "dt",
    "uf",
    "cases",
    "icu_known",
    "icu_admissions",
    "outcome_known",
    "deaths",
    "vaccination_known",
    "vaccinated",
    "cases_influenza",
    "cases_other_virus",
    "cases_other_agent",
    "cases_unspecified",
    "cases_covid",
}


@pytest.fixture
def settings(tmp_path) -> Settings:
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "INFLUD26-test.csv").write_text("\n".join([HEADER, *ROWS]), encoding="utf-8")
    return Settings(data_dir=tmp_path, audit_log_path=tmp_path / "audit.jsonl")


@pytest.fixture
def marts(settings):
    return build_marts(settings, AuditLogger(settings.audit_log_path))


@pytest.fixture
def con(settings):
    """Conexão com `stg_cases` e `int_cases` já criadas (o tratamento é em memória)."""
    audit = AuditLogger(settings.audit_log_path)
    csv_files = sorted(settings.staging_dir.glob("INFLUD*.csv"))
    with duckdb.connect() as connection:
        load_staging(connection, csv_files, audit)
        clean_cases(connection, audit)
        yield connection


def test_clean_cases_applies_every_rule(con):
    rows = con.sql(
        "SELECT uf, hospital, evolucao, vacina_cov, classi_fin FROM int_cases ORDER BY dt_notific"
    ).fetchall()
    # duplicata removida (fica o desfecho conhecido), internação inferida pela UTI,
    # vacina 9 -> nulo, UF inválida e classificação 9 -> nulo.
    assert rows == [("SP", 1, 2, 1, 5), ("RJ", 1, 1, None, 1), (None, 1, 2, 2, None)]


def test_quality_report_counts_every_rule(con):
    quality = quality_report(con)
    assert quality["linhas_staging"] == 6
    assert quality["descartadas_data_invalida"] == 2
    assert quality["descartadas_duplicadas"] == 1
    assert quality["linhas_tratadas"] == 3
    assert quality["hospital_inferido_por_uti"] == 1  # só a linha do RJ (internação 9, UTI = 1)
    assert quality["vacina_ignorada_para_nulo"] == 1
    assert quality["hospital_ignorado_para_nulo"] == 1
    assert quality["classi_fin_ignorada_para_nulo"] == 1
    assert quality["ausentes_classi_fin"] == 1
    assert quality["ausentes_uf"] == 1


def test_marts_are_aggregated_without_identifiers(marts):
    daily = marts.daily
    assert int(daily["cases"].sum()) == 3
    assert int(daily["cases_covid"].sum()) == 1
    assert int(daily["cases_influenza"].sum()) == 1
    assert int(marts.monthly["cases"].sum()) == 3
    assert set(daily.columns) == MART_COLUMNS
    assert set(marts.monthly.columns) == {"month", "uf", "cases"}
    # Contagens precisam ser inteiras (o Postgres rejeita "2.0" em colunas bigint).
    assert str(marts.monthly["cases"].dtype).startswith("int")
    assert all(
        str(marts.daily[column].dtype).startswith("int") for column in MART_COLUMNS - {"dt", "uf"}
    )
    assert marts.quality["linhas_tratadas"] == 3


def test_pipeline_writes_nothing_to_disk_besides_the_audit_log(marts, settings, tmp_path):
    produced = {path for path in tmp_path.rglob("*") if path.is_file()}
    expected = {settings.audit_log_path, *settings.staging_dir.glob("INFLUD*.csv")}
    assert produced == expected  # nenhum Parquet nem arquivo de dados derivado


def test_missing_staging_files_raise_a_clear_error(tmp_path):
    settings = Settings(data_dir=tmp_path, audit_log_path=tmp_path / "audit.jsonl")
    (tmp_path / "staging").mkdir()
    with pytest.raises(FileNotFoundError, match="INFLUD"):
        build_marts(settings, AuditLogger(settings.audit_log_path))


def test_sensitive_column_guard_blocks_sql():
    assert_no_sensitive_columns("SELECT uf FROM stg_cases", "ok.sql")
    with pytest.raises(PermissionError, match="NU_CPF"):
        assert_no_sensitive_columns("SELECT nu_cpf FROM staging", "bad.sql")
