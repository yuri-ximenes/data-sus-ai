"""Métricas e séries temporais calculadas a partir dos marts agregados.

O mart diário (`dt`, `uf`, contagens) é filtrado pela janela terminando em `as_of`; as taxas
são razões entre somas dessas contagens. A data usada é a de notificação.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import pandas as pd

YEAR_SHIFT_DAYS = 364  # 52 semanas: o mesmo dia da semana um ano antes
MIN_CASES_FOR_GROWTH = 100  # abaixo disso a variação percentual por UF é pouco confiável
ETIOLOGY_COLUMNS = {
    "cases_influenza": "Influenza",
    "cases_other_virus": "Outro vírus respiratório",
    "cases_other_agent": "Outro agente etiológico",
    "cases_unspecified": "Não especificado",
    "cases_covid": "COVID-19",
}


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


def _scope(frame: pd.DataFrame, uf: str | None) -> pd.DataFrame:
    return frame if uf is None else frame[frame["uf"] == uf]


def _window(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return frame[(frame["dt"] >= pd.Timestamp(start)) & (frame["dt"] <= pd.Timestamp(end))]


def _total(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].sum())


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def _rate_metric(key: str, name: str, numerator: int, denominator: int, description: str) -> Metric:
    return Metric(key, name, _percent(numerator, denominator), numerator, denominator, description)


def case_growth_rate(daily: pd.DataFrame, as_of: date, days: int) -> Metric:
    current_start = as_of - timedelta(days=days - 1)
    previous_start = current_start - timedelta(days=days)
    current = _total(_window(daily, current_start, as_of), "cases")
    previous = _total(_window(daily, previous_start, current_start - timedelta(days=1)), "cases")
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


def mortality_rate(daily: pd.DataFrame, as_of: date, days: int) -> Metric:
    window = _window(daily, as_of - timedelta(days=days - 1), as_of)
    return _rate_metric(
        "taxa_mortalidade",
        "Taxa de mortalidade",
        _total(window, "deaths"),
        _total(window, "outcome_known"),
        f"Óbitos por SRAG / casos com desfecho conhecido, notificados nos últimos {days} dias.",
    )


def icu_rate(daily: pd.DataFrame, as_of: date, days: int) -> Metric:
    window = _window(daily, as_of - timedelta(days=days - 1), as_of)
    return _rate_metric(
        "taxa_ocupacao_uti",
        "Taxa de ocupação de UTI",
        _total(window, "icu_admissions"),
        _total(window, "icu_known"),
        "Proxy: internações por SRAG que passaram por UTI / internações com informação de UTI, "
        f"últimos {days} dias. Não considera a capacidade total de leitos.",
    )


def vaccination_rate(daily: pd.DataFrame, as_of: date, days: int) -> Metric:
    window = _window(daily, as_of - timedelta(days=days - 1), as_of)
    return _rate_metric(
        "taxa_vacinacao",
        "Taxa de vacinação (COVID-19)",
        _total(window, "vaccinated"),
        _total(window, "vaccination_known"),
        "Proxy: casos de SRAG que receberam vacina COVID-19 / casos com informação vacinal, "
        f"últimos {days} dias. Não é cobertura vacinal da população geral.",
    )


def compute_all(daily: pd.DataFrame, as_of: date, days: int, uf: str | None = None) -> list[Metric]:
    scoped = _scope(daily, uf)
    return [
        case_growth_rate(scoped, as_of, days),
        year_over_year_change(scoped, as_of, days),
        mortality_rate(scoped, as_of, days),
        icu_rate(scoped, as_of, days),
        vaccination_rate(scoped, as_of, days),
    ]


def year_over_year_change(daily: pd.DataFrame, as_of: date, days: int) -> Metric:
    """Compara a janela atual com a mesma janela 52 semanas antes (mesmos dias da semana)."""
    shift = timedelta(days=YEAR_SHIFT_DAYS)
    current_start = as_of - timedelta(days=days - 1)
    current = _total(_window(daily, current_start, as_of), "cases")
    previous = _total(_window(daily, current_start - shift, as_of - shift), "cases")
    value = round(100 * (current - previous) / previous, 1) if previous else None
    return Metric(
        "variacao_ano_anterior",
        "Variação vs. mesmo período do ano anterior",
        value,
        current,
        previous,
        f"Casos dos últimos {days} dias vs. a mesma janela 52 semanas antes (sazonalidade). "
        "Dias recentes ainda sofrem atraso de notificação, o que tende a subestimar o valor.",
    )


@dataclass(frozen=True)
class EtiologyBreakdown:
    table: pd.DataFrame  # colunas: agente, casos, percentual (sobre os casos classificados)
    classified: int
    unclassified: int  # casos recentes ainda sem classificação final


def etiology_breakdown(
    daily: pd.DataFrame, as_of: date, days: int, uf: str | None = None
) -> EtiologyBreakdown:
    window = _window(_scope(daily, uf), as_of - timedelta(days=days - 1), as_of)
    counts = {label: _total(window, column) for column, label in ETIOLOGY_COLUMNS.items()}
    classified = sum(counts.values())
    table = pd.DataFrame(
        [
            {"agente": label, "casos": count, "percentual": _percent(count, classified)}
            for label, count in counts.items()
        ]
    )
    return EtiologyBreakdown(table, classified, _total(window, "cases") - classified)


def uf_summary(daily: pd.DataFrame, as_of: date, days: int) -> pd.DataFrame:
    """Casos por UF na janela atual e na anterior, com a variação percentual."""
    current_start = as_of - timedelta(days=days - 1)
    previous_start = current_start - timedelta(days=days)
    current = _window(daily, current_start, as_of).groupby("uf")["cases"].sum()
    previous = _window(daily, previous_start, current_start - timedelta(days=1))
    previous = previous.groupby("uf")["cases"].sum()
    table = pd.DataFrame({"casos": current, "casos_anteriores": previous}).fillna(0).astype(int)
    baseline = table["casos_anteriores"].where(table["casos_anteriores"] > 0)
    table["variacao_pct"] = (100 * (table["casos"] - baseline) / baseline).round(1)
    return table.rename_axis("uf").reset_index()


def top_ufs_by_cases(summary: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    return summary.nlargest(n, "casos").reset_index(drop=True)


def top_ufs_by_growth(
    summary: pd.DataFrame, n: int = 5, min_cases: int = MIN_CASES_FOR_GROWTH
) -> pd.DataFrame:
    """UFs com maior crescimento, ignorando as de poucos casos (variação instável)."""
    eligible = summary[summary["casos"] >= min_cases].dropna(subset=["variacao_pct"])
    return eligible.nlargest(n, "variacao_pct").reset_index(drop=True)


def daily_series(daily: pd.DataFrame, as_of: date, days: int = 30, uf: str | None = None):
    start = as_of - timedelta(days=days - 1)
    counts = _window(_scope(daily, uf), start, as_of).groupby("dt")["cases"].sum()
    index = pd.date_range(start, as_of, freq="D")
    return counts.reindex(index, fill_value=0).rename_axis("data").rename("casos")


def monthly_series(monthly: pd.DataFrame, as_of: date, months: int = 12, uf: str | None = None):
    scoped = _scope(monthly, uf)
    index = pd.period_range(end=pd.Period(as_of, freq="M"), periods=months, freq="M")
    counts = scoped.groupby(scoped["month"].dt.to_period("M"))["cases"].sum()
    return counts.reindex(index, fill_value=0).sort_index()
