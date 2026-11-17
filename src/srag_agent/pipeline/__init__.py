"""Pipeline de dados: staging (CSV) -> tratamento em memória -> marts agregados (Parquet)."""

from srag_agent.pipeline.runner import needs_rebuild, run_pipeline
from srag_agent.pipeline.warehouse import load_daily_summary, load_monthly_summary, load_quality

__all__ = [
    "load_daily_summary",
    "load_monthly_summary",
    "load_quality",
    "needs_rebuild",
    "run_pipeline",
]
