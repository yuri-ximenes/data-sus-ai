import pandas as pd

from srag_agent.charts import month_label


def test_month_label_is_portuguese_abbreviation_with_two_digit_year():
    assert month_label(pd.Period("2026-02", freq="M")) == "fev-26"
    assert month_label(pd.Period("2025-12", freq="M")) == "dez-25"
    assert month_label(pd.Period("2026-05", freq="M")) == "mai-26"
