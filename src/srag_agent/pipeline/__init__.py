"""Pipeline de dados: staging (CSV) -> tratamento em memória -> marts agregados no Supabase."""

from srag_agent.pipeline.runner import Marts, build_marts
from srag_agent.pipeline.supabase import (
    publish_marts,
    read_daily_summary,
    read_monthly_summary,
    read_quality,
)

__all__ = [
    "Marts",
    "build_marts",
    "publish_marts",
    "read_daily_summary",
    "read_monthly_summary",
    "read_quality",
]
