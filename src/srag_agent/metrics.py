"""Cálculo das métricas e séries temporais a partir dos casos tratados.

Todas as métricas usam a data de notificação (DT_NOTIFIC) e a janela terminando em `as_of`.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import pandas as pd


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    value: float | None  # em %, ou None quando não há denominador
    numerator: int
    denominator: int
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


def _between(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    dates = frame["dt_notific"].dt.date
    return frame[(dates >= start) & (dates <= end)]


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def case_growth_rate(frame: pd.DataFrame, as_of: date, days: int) -> Metric:
    current_start = as_of - timedelta(days=days - 1)
    previous_start = current_start - timedelta(days=days)
    current = len(_between(frame, current_start, as_of))
    previous = len(_between(frame, previous_start, current_start - timedelta(days=1)))
    value = round(100 * (current - previous) / previous, 1) if previous else None
    return Metric(
        "taxa_aumento_casos",
        "Taxa de aumento de casos",
        value,
        current,
        previous,
        f"Variação % dos casos notificados nos últimos {days} dias vs. os {days} dias anteriores "
        "(numerador = casos atuais; denominador = casos do período anterior).",
    )


def mortality_rate(frame: pd.DataFrame, as_of: date, days: int) -> Metric:
    window = _between(frame, as_of - timedelta(days=days - 1), as_of)
    closed = window["evolucao"].notna()
    deaths = int((window["evolucao"] == 2).sum())
    return Metric(
        "taxa_mortalidade",
        "Taxa de mortalidade",
        _ratio(deaths, int(closed.sum())),
        deaths,
        int(closed.sum()),
        f"Óbitos por SRAG / casos com desfecho conhecido, notificados nos últimos {days} dias.",
    )


def icu_rate(frame: pd.DataFrame, as_of: date, days: int) -> Metric:
    window = _between(frame, as_of - timedelta(days=days - 1), as_of)
    known = window[(window["hospital"] == 1) & window["uti"].notna()]
    in_icu = int((known["uti"] == 1).sum())
    return Metric(
        "taxa_ocupacao_uti",
        "Taxa de ocupação de UTI",
        _ratio(in_icu, len(known)),
        in_icu,
        len(known),
        f"Proxy: internações por SRAG que passaram por UTI / internações com informação de UTI, "
        f"últimos {days} dias. Não considera a capacidade total de leitos.",
    )


def vaccination_rate(frame: pd.DataFrame, as_of: date, days: int) -> Metric:
    window = _between(frame, as_of - timedelta(days=days - 1), as_of)
    known = window[window["vacina_cov"].notna()]
    vaccinated = int((known["vacina_cov"] == 1).sum())
    return Metric(
        "taxa_vacinacao",
        "Taxa de vacinação (COVID-19)",
        _ratio(vaccinated, len(known)),
        vaccinated,
        len(known),
        f"Proxy: casos de SRAG que receberam vacina COVID-19 / casos com informação vacinal, "
        f"últimos {days} dias. Não é cobertura vacinal da população geral.",
    )


def compute_all(frame: pd.DataFrame, as_of: date, days: int, uf: str | None = None) -> list[Metric]:
    scoped = frame if uf is None else frame[frame["uf"] == uf]
    return [
        case_growth_rate(scoped, as_of, days),
        mortality_rate(scoped, as_of, days),
        icu_rate(scoped, as_of, days),
        vaccination_rate(scoped, as_of, days),
    ]


def daily_series(frame: pd.DataFrame, as_of: date, days: int = 30, uf: str | None = None):
    scoped = frame if uf is None else frame[frame["uf"] == uf]
    start = as_of - timedelta(days=days - 1)
    counts = _between(scoped, start, as_of).groupby(scoped["dt_notific"].dt.date).size()
    index = pd.date_range(start, as_of, freq="D").date
    return counts.reindex(index, fill_value=0).rename_axis("data").rename("casos")


def monthly_series(frame: pd.DataFrame, as_of: date, months: int = 12, uf: str | None = None):
    scoped = frame if uf is None else frame[frame["uf"] == uf]
    last = pd.Period(as_of, freq="M")
    index = pd.period_range(end=last, periods=months, freq="M")
    periods = scoped["dt_notific"].dt.to_period("M")
    return periods[periods.isin(index)].value_counts().reindex(index, fill_value=0).sort_index()
