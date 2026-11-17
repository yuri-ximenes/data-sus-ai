"""Geração dos gráficos do relatório (matplotlib, backend sem interface)."""

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from srag_agent.metrics import daily_series, monthly_series  # noqa: E402

COLOR = "#1f6f8b"
DAILY_DATE_FORMAT = "%d-%m-%Y"  # ex.: 17-10-2026
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def month_label(period: pd.Period) -> str:
    """Rótulo do mês em português e independente de locale, ex.: fev-26."""
    return f"{MONTHS_PT[period.month - 1]}-{period.year % 100:02d}"


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_daily(daily: pd.DataFrame, as_of: date, out_dir: Path, uf: str | None, days: int = 30):
    series = daily_series(daily, as_of, days, uf)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(pd.to_datetime(series.index), series.values, color=COLOR, marker="o", markersize=3)
    ax.set_title(f"Casos diários de SRAG - últimos {days} dias ({uf or 'Brasil'})")
    ax.set_ylabel("Casos notificados")
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(DAILY_DATE_FORMAT))
    fig.autofmt_xdate()
    return _save(fig, out_dir / f"casos_diarios_{as_of}.png")


def plot_monthly(
    monthly: pd.DataFrame, as_of: date, out_dir: Path, uf: str | None, months: int = 12
):
    series = monthly_series(monthly, as_of, months, uf)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    labels = [month_label(period) for period in series.index]
    ax.bar(labels, series.values, color=COLOR)
    ax.set_title(f"Casos mensais de SRAG - últimos {months} meses ({uf or 'Brasil'})")
    ax.set_ylabel("Casos notificados")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)
    ax.annotate(
        "último mês parcial",
        (len(labels) - 1, series.values[-1]),
        ha="center",
        va="bottom",
        fontsize=8,
    )
    return _save(fig, out_dir / f"casos_mensais_{as_of}.png")
