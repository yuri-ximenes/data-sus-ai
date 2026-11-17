"""Leitura dos marts (camada de consumo). O agente só enxerga dados agregados."""

import json

import duckdb
import pandas as pd

from srag_agent.config import Settings


def _read_parquet(path) -> pd.DataFrame:
    with duckdb.connect() as con:
        return con.sql("SELECT * FROM read_parquet($path)", params={"path": str(path)}).df()


def load_daily_summary(settings: Settings) -> pd.DataFrame:
    frame = _read_parquet(settings.daily_mart_file)
    frame["dt"] = pd.to_datetime(frame["dt"])
    return frame


def load_monthly_summary(settings: Settings) -> pd.DataFrame:
    frame = _read_parquet(settings.monthly_mart_file)
    frame["month"] = pd.to_datetime(frame["month"])
    return frame


def load_quality(settings: Settings) -> dict[str, int]:
    return json.loads(settings.quality_report_file.read_text(encoding="utf-8"))
