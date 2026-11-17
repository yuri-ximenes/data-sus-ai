"""Executa a pipeline com DuckDB, inteiramente em memória, em três camadas.

staging      CSVs em data/staging, lidos e tipados          -> stg_cases   (sql/staging)
intermediate tratamento: regras de qualidade e deduplicação -> int_cases   (sql/intermediate)
marts        contagens agregadas, sem dado individual       -> mart_daily, mart_monthly (sql/marts)

Nada é gravado em disco: só os marts seguem para o Supabase (ver `supabase.publish_marts`).
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


def _read_sql(layer: str, name: str) -> str:
    sql = (SQL_DIR / layer / f"{name}.sql").read_text(encoding="utf-8")
    assert_no_sensitive_columns(sql, f"{layer}/{name}.sql")
    return sql


def _create_temp_table(
    con: duckdb.DuckDBPyConnection,
    table: str,
    layer: str,
    sql_file: str,
    params: dict,
    audit: AuditLogger,
) -> None:
    started = time.perf_counter()
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} AS " + _read_sql(layer, sql_file), params)
    audit.log(
        "pipeline_layer",
        layer=layer,
        output=f"{table} (em memória)",
        rows=con.sql(f"SELECT count(*) FROM {table}").fetchall()[0][0],
        duration_s=round(time.perf_counter() - started, 2),
    )


def load_staging(con: duckdb.DuckDBPyConnection, csv_files: list[Path], audit: AuditLogger) -> None:
    """Camada staging: lê os CSVs para `stg_cases` (colunas úteis, renomeadas e tipadas)."""
    params = {"files": [str(path) for path in csv_files]}
    _create_temp_table(con, "stg_cases", "staging", "stg_srag_cases", params, audit)


def clean_cases(con: duckdb.DuckDBPyConnection, audit: AuditLogger) -> None:
    """Camada intermediate: aplica o tratamento e gera `int_cases` (um caso válido por linha)."""
    params = {"valid_ufs": sorted(VALID_UFS)}
    _create_temp_table(con, "int_cases", "intermediate", "int_srag_cases_clean", params, audit)


def quality_report(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Contagens antes/depois do tratamento (exige `stg_cases` e `int_cases`)."""
    row = con.sql(_read_sql("marts", "quality_report"), params={"valid_ufs": sorted(VALID_UFS)})
    report = {key: int(value) for key, value in row.fetchdf().iloc[0].items()}
    report["descartadas_duplicadas"] = (
        report["linhas_staging"] - report["descartadas_data_invalida"] - report["linhas_tratadas"]
    )
    return report


def build_marts(settings: Settings, audit: AuditLogger) -> Marts:
    """staging -> intermediate (tratamento) -> marts agregados."""
    csv_files = list_csv_files(settings.staging_dir)
    audit.log("pipeline_start", sources=[path.name for path in csv_files])
    with duckdb.connect() as con:
        load_staging(con, csv_files, audit)
        clean_cases(con, audit)
        _create_temp_table(con, "mart_daily", "marts", "mart_srag_daily_summary", {}, audit)
        daily = con.sql("SELECT * FROM mart_daily").df()
        monthly = con.sql(_read_sql("marts", "mart_srag_monthly_summary")).df()
        quality = quality_report(con)
    audit.log("data_quality", **quality)
    return Marts(daily=daily, monthly=monthly, quality=quality)
