"""Marts sintéticos compartilhados pelos testes."""

import pandas as pd

DAILY_COLUMNS = [
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
]


def day(dt: str, uf: str, cases: int, **values: int) -> dict:
    """Uma linha do mart diário; colunas não informadas ficam em zero."""
    row = dict.fromkeys(DAILY_COLUMNS, 0)
    row.update(dt=dt, uf=uf, cases=cases, **values)
    return row


def make_daily(*rows: dict) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=DAILY_COLUMNS)
    frame["dt"] = pd.to_datetime(frame["dt"])
    return frame


def daily_summary() -> pd.DataFrame:
    """SP: 10 casos no período atual, 5 no anterior e 8 na mesma janela do ano anterior."""
    return make_daily(
        day(
            "2026-11-10",
            "SP",
            10,
            icu_known=5,
            icu_admissions=2,
            outcome_known=3,
            deaths=2,
            vaccination_known=10,
            vaccinated=5,
            cases_influenza=2,
            cases_other_virus=3,
            cases_other_agent=1,
            cases_unspecified=2,
            cases_covid=1,
        ),
        day("2026-10-05", "SP", 5),
        day("2025-11-10", "SP", 8),
    )


def monthly_summary() -> pd.DataFrame:
    frame = pd.DataFrame(
        [("2026-11-01", "SP", 10), ("2026-10-01", "SP", 5)], columns=["month", "uf", "cases"]
    )
    frame["month"] = pd.to_datetime(frame["month"])
    return frame
