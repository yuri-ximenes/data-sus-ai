"""Executa a pipeline com DuckDB, inteiramente em memória.

staging (CSVs em data/staging) -> tratamento -> marts agregados (DataFrames).
Nada é gravado em disco: os marts seguem direto para o banco (ver `supabase.publish_marts`).
"""

import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from srag_agent.audit import AuditLogger
from srag_agent.config import VALID_UFS, Settings
from srag_agent.pipeline.sensitive import assert_no_sensitive_columns

SQL_DIR = Path(__file__).parent / "sql"


@dataclass(frozen=True)
class Marts:
    """Resultado da pipeline: contagens agregadas e o relatório de qualidade."""

    daily: pd.DataFrame
    monthly: pd.DataFrame
    quality: dict[str, int]


def list_csv_files(staging_dir: Path) -> list[Path]:
    files = sorted(staging_dir.glob("INFLUD*.csv"))
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo INFLUD*.csv encontrado em {staging_dir}")
    return files


def _read_sql(name: str) -> str:
    sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    assert_no_sensitive_columns(sql, f"{name}.sql")
    return sql


def _create_temp_table(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sql_file: str,
    params: dict,
    layer: str,
    audit: AuditLogger,
) -> None:
    started = time.perf_counter()
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} AS " + _read_sql(sql_file), params)
    audit.log(
        "pipeline_layer",
        layer=layer,
        output=f"{table} (em memória)",
        rows=con.sql(f"SELECT count(*) FROM {table}").fetchall()[0][0],
        duration_s=round(time.perf_counter() - started, 2),
    )


def load_staging(con: duckdb.DuckDBPyConnection, csv_files: list[Path], audit: AuditLogger) -> None:
    """Lê os CSVs do staging para `typed_cases`: colunas úteis, renomeadas e tipadas."""
    params = {"files": [str(path) for path in csv_files]}
    _create_temp_table(con, "typed_cases", "typed_srag_cases", params, "staging", audit)


def clean_cases(con: duckdb.DuckDBPyConnection, audit: AuditLogger) -> None:
    """Aplica as regras de qualidade e gera `clean_cases` (uma linha por caso válido)."""
    params = {"valid_ufs": sorted(VALID_UFS)}
    _create_temp_table(con, "clean_cases", "clean_srag_cases", params, "tratamento", audit)


def quality_report(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Contagens antes/depois do tratamento (exige `typed_cases` e `clean_cases`)."""
    row = con.sql(_read_sql("quality_report"), params={"valid_ufs": sorted(VALID_UFS)})
    report = {key: int(value) for key, value in row.fetchdf().iloc[0].items()}
    report["descartadas_duplicadas"] = (
        report["linhas_staging"] - report["descartadas_data_invalida"] - report["linhas_tratadas"]
    )
    return report


def build_marts(settings: Settings, audit: AuditLogger) -> Marts:
    """Constrói os marts agregados a partir dos CSVs do staging."""
    csv_files = list_csv_files(settings.staging_dir)
    audit.log("pipeline_start", sources=[path.name for path in csv_files])
    with duckdb.connect() as con:
        load_staging(con, csv_files, audit)
        clean_cases(con, audit)
        _create_temp_table(con, "daily_mart", "mart_srag_daily_summary", {}, "mart_daily", audit)
        daily = con.sql("SELECT * FROM daily_mart").df()
        monthly = con.sql(_read_sql("mart_srag_monthly_summary")).df()
        quality = quality_report(con)
    audit.log("data_quality", **quality)
    return Marts(daily=daily, monthly=monthly, quality=quality)
