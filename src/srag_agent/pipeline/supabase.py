"""Backend opcional: marts agregados em um Postgres (Supabase).

- Só contagens agregadas por data e UF vão para o banco; nenhum dado individual.
- O LLM nunca escreve SQL: as tools usam as consultas fixas deste módulo, somente leitura.
- A string de conexão vem de `SUPABASE_DB_URL` e nunca é gravada em log nem em mensagem de erro.
"""

import os
import time

import pandas as pd
import psycopg

from srag_agent.audit import AuditLogger

URL_VARIABLE = "SUPABASE_DB_URL"
SCHEMA = "srag"  # schema próprio: não é exposto pela API REST pública do Supabase
CONNECTION_ERROR = (
    f"Falha ao conectar ao banco. Verifique {URL_VARIABLE} "
    "e se o projeto Supabase não está pausado."
)

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
MONTHLY_COLUMNS = ["month", "uf", "cases"]

DDL = [
    f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
    f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.mart_daily_summary (
        dt date NOT NULL, uf text, cases bigint NOT NULL, icu_known bigint NOT NULL,
        icu_admissions bigint NOT NULL, outcome_known bigint NOT NULL, deaths bigint NOT NULL,
        vaccination_known bigint NOT NULL, vaccinated bigint NOT NULL,
        cases_influenza bigint NOT NULL, cases_other_virus bigint NOT NULL,
        cases_other_agent bigint NOT NULL, cases_unspecified bigint NOT NULL,
        cases_covid bigint NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.mart_monthly_summary (
        month date NOT NULL, uf text, cases bigint NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.quality_report (
        metric text PRIMARY KEY, value bigint NOT NULL)""",
    # RLS ligado e sem políticas: papéis da API pública (anon/authenticated) não leem nada.
    f"ALTER TABLE {SCHEMA}.mart_daily_summary ENABLE ROW LEVEL SECURITY",
    f"ALTER TABLE {SCHEMA}.mart_monthly_summary ENABLE ROW LEVEL SECURITY",
    f"ALTER TABLE {SCHEMA}.quality_report ENABLE ROW LEVEL SECURITY",
]

# Consultas fixas e somente leitura usadas pelas tools (o LLM não escreve SQL).
SELECT_DAILY = f"SELECT {', '.join(DAILY_COLUMNS)} FROM {SCHEMA}.mart_daily_summary ORDER BY dt, uf"
SELECT_MONTHLY = f"SELECT {', '.join(MONTHLY_COLUMNS)} FROM {SCHEMA}.mart_monthly_summary"
SELECT_QUALITY = f"SELECT metric, value FROM {SCHEMA}.quality_report"


def connect() -> psycopg.Connection:
    """Abre a conexão; funciona também com o pooler do Supabase (modo transação)."""
    url = os.getenv(URL_VARIABLE)
    if not url:
        raise RuntimeError(f"Variável {URL_VARIABLE} ausente. Veja env.example.")
    try:
        return psycopg.connect(url, sslmode="require", prepare_threshold=None, connect_timeout=15)
    except psycopg.OperationalError:
        raise RuntimeError(CONNECTION_ERROR) from None  # sem detalhes: podem expor host/usuário


def _read(query: str) -> list[tuple]:
    with connect() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(query)
        return cur.fetchall()


def read_daily_summary() -> pd.DataFrame:
    frame = pd.DataFrame(_read(SELECT_DAILY), columns=DAILY_COLUMNS)
    frame["dt"] = pd.to_datetime(frame["dt"])
    return frame


def read_monthly_summary() -> pd.DataFrame:
    frame = pd.DataFrame(_read(SELECT_MONTHLY), columns=MONTHLY_COLUMNS)
    frame["month"] = pd.to_datetime(frame["month"])
    return frame


def read_quality() -> dict[str, int]:
    return {metric: int(value) for metric, value in _read(SELECT_QUALITY)}


def _records(frame: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """Linhas com tipos nativos do Python (datas como `date`, NaN como None)."""
    prepared = frame[columns].copy()
    for column in ("dt", "month"):
        if column in prepared:
            prepared[column] = prepared[column].dt.date
    prepared = prepared.astype(object).where(prepared.notna(), None)
    return [tuple(row) for row in prepared.itertuples(index=False, name=None)]


def _replace_table(cur, table: str, columns: list[str], rows: list[tuple]) -> None:
    cur.execute(f"TRUNCATE {SCHEMA}.{table}")
    with cur.copy(f"COPY {SCHEMA}.{table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def publish_marts(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    quality: dict[str, int],
    audit: AuditLogger,
) -> None:
    """Substitui o conteúdo dos marts no banco, em uma única transação."""
    started = time.perf_counter()
    daily_rows = _records(daily, DAILY_COLUMNS)
    monthly_rows = _records(monthly, MONTHLY_COLUMNS)
    with connect() as conn, conn.transaction(), conn.cursor() as cur:
        for statement in DDL:
            cur.execute(statement)
        _replace_table(cur, "mart_daily_summary", DAILY_COLUMNS, daily_rows)
        _replace_table(cur, "mart_monthly_summary", MONTHLY_COLUMNS, monthly_rows)
        _replace_table(cur, "quality_report", ["metric", "value"], list(quality.items()))
    audit.log(
        "database_publish",
        backend="supabase",
        schema=SCHEMA,
        rows={
            "mart_daily_summary": len(daily_rows),
            "mart_monthly_summary": len(monthly_rows),
            "quality_report": len(quality),
        },
        duration_s=round(time.perf_counter() - started, 2),
    )
