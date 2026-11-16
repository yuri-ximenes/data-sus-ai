"""Configurações centrais da aplicação."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Deve rodar antes da definição de Settings, cujos padrões leem variáveis de ambiente.
load_dotenv(PROJECT_ROOT / ".env")

VALID_UFS = frozenset(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)


@dataclass(frozen=True)
class Settings:
    """Parâmetros de execução. Valores sensíveis (chaves de API) vêm só do ambiente."""

    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    output_dir: Path = PROJECT_ROOT / "reports"
    audit_log_path: Path = PROJECT_ROOT / "logs" / "audit.jsonl"
    provider: str = os.getenv("SRAG_PROVIDER", "gemini")
    model_name: str = os.getenv("SRAG_MODEL", "")  # vazio = padrão do provedor
    window_days: int = 30
    chart_months: int = 12
    max_news_items: int = 8
    news_max_age_days: int = 30
    max_guardrail_retries: int = 2
    agent_recursion_limit: int = 25
