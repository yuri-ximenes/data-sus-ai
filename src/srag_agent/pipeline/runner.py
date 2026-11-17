"""Executa a pipeline com DuckDB.

staging (CSVs em data/staging) -> tratamento em memória -> marts agregados (Parquet).
Nenhum dado individual é gravado em disco: só os marts e o relatório de qualidade.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

from srag_agent.audit import AuditLogger
from srag_agent.config import VALID_UFS, Settings
from srag_agent.pipeline.sensitive import assert_no_sensitive_columns

SQL_DIR = Path(__file__).parent / "sql"


@dataclass(frozen=True)
class Mart:
    name: str
    sql_file: str
    output: Path
    params: dict


def list_csv_files(staging_dir: Path) -> list[Path]:
    files = sorted(staging_dir.glob("INFLUD*.csv"))
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo INFLUD*.csv encontrado em {staging_dir}")
    return files


def needs_rebuild(settings: Settings) -> bool:
    """True se os marts não existem ou algum CSV do staging é mais novo que eles."""
    marts = [settings.daily_mart_file, settings.monthly_mart_file, settings.quality_report_file]
    if not all(path.exists() for path in marts):
        return True
    newest_csv = max(path.stat().st_mtime for path in list_csv_files(settings.staging_dir))
    return newest_csv > min(path.stat().st_mtime for path in marts)


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


def _build_marts(settings: Settings) -> list[Mart]:
    return [
        Mart("mart_daily", "mart_srag_daily_summary", settings.daily_mart_file, {}),
        Mart(
            "mart_monthly",
            "mart_srag_monthly_summary",
            settings.monthly_mart_file,
            {"input": str(settings.daily_mart_file)},
        ),
    ]


def _write_mart(con: duckdb.DuckDBPyConnection, mart: Mart, audit: AuditLogger) -> None:
    started = time.perf_counter()
    mart.output.parent.mkdir(parents=True, exist_ok=True)
    con.sql(_read_sql(mart.sql_file), params=mart.params).write_parquet(str(mart.output))
    rows = con.sql("SELECT count(*) FROM read_parquet($path)", params={"path": str(mart.output)})
    audit.log(
        "pipeline_layer",
        layer=mart.name,
        output=mart.output.name,
        rows=rows.fetchall()[0][0],
        duration_s=round(time.perf_counter() - started, 2),
    )


def quality_report(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Contagens antes/depois do tratamento (exige `typed_cases` e `clean_cases`)."""
    row = con.sql(_read_sql("quality_report"), params={"valid_ufs": sorted(VALID_UFS)})
    report = {key: int(value) for key, value in row.fetchdf().iloc[0].items()}
    report["descartadas_duplicadas"] = (
        report["linhas_staging"] - report["descartadas_data_invalida"] - report["linhas_tratadas"]
    )
    return report


def run_pipeline(settings: Settings, audit: AuditLogger) -> dict[str, int]:
    """Constrói os marts a partir do staging; persiste o relatório de qualidade."""
    csv_files = list_csv_files(settings.staging_dir)
    audit.log("pipeline_start", sources=[path.name for path in csv_files])
    with duckdb.connect() as con:
        load_staging(con, csv_files, audit)
        clean_cases(con, audit)
        for mart in _build_marts(settings):
            _write_mart(con, mart, audit)
        quality = quality_report(con)
    settings.quality_report_file.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    audit.log("data_quality", **quality)
    return quality
