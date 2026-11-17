"""Backend Supabase testado com um banco simulado (sem rede nem credenciais)."""

from contextlib import nullcontext
from datetime import date

import psycopg
import pytest

from frames import day, make_daily, monthly_summary
from srag_agent.audit import AuditLogger
from srag_agent.pipeline import supabase


class FakeCopy:
    def __init__(self, rows: list) -> None:
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write_row(self, row: tuple) -> None:
        self.rows.append(row)


class FakeDatabase:
    """Registra o que foi executado e devolve respostas pré-definidas por consulta."""

    def __init__(self, responses: dict | None = None) -> None:
        self.responses = responses or {}
        self.statements: list[str] = []
        self.copied: dict[str, list] = {}


class FakeCursor:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db
        self.result: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str) -> None:
        self.db.statements.append(sql)
        self.result = self.db.responses.get(sql, [])

    def fetchall(self) -> list:
        return self.result

    def copy(self, sql: str) -> FakeCopy:
        return FakeCopy(self.db.copied.setdefault(sql, []))


class FakeConnection:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def transaction(self):
        return nullcontext()

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.db)


@pytest.fixture
def fake_db(monkeypatch) -> FakeDatabase:
    db = FakeDatabase()
    monkeypatch.setattr(supabase, "connect", lambda: FakeConnection(db))
    return db


def test_connect_requires_the_url_variable(monkeypatch):
    monkeypatch.delenv(supabase.URL_VARIABLE, raising=False)
    with pytest.raises(RuntimeError, match=supabase.URL_VARIABLE):
        supabase.connect()


def test_connection_failure_does_not_leak_host_or_password(monkeypatch):
    monkeypatch.setenv(supabase.URL_VARIABLE, "postgresql://user:s3cret@secret-host:6543/db")

    def refuse(*args, **kwargs):
        raise psycopg.OperationalError("could not connect to secret-host with s3cret")

    monkeypatch.setattr(psycopg, "connect", refuse)
    with pytest.raises(RuntimeError) as error:
        supabase.connect()
    assert "secret-host" not in str(error.value) and "s3cret" not in str(error.value)


def test_reads_run_in_a_read_only_transaction(fake_db):
    fake_db.responses[supabase.SELECT_DAILY] = [
        (date(2026, 11, 10), "SP", 10, 5, 2, 3, 2, 10, 5, 2, 3, 1, 2, 1)
    ]
    frame = supabase.read_daily_summary()
    assert fake_db.statements == ["SET TRANSACTION READ ONLY", supabase.SELECT_DAILY]
    assert list(frame.columns) == supabase.DAILY_COLUMNS
    assert str(frame["dt"].dtype).startswith("datetime64")
    assert int(frame.loc[0, "cases"]) == 10


def test_read_quality_returns_a_dictionary(fake_db):
    fake_db.responses[supabase.SELECT_QUALITY] = [("linhas_staging", 6), ("linhas_tratadas", 3)]
    assert supabase.read_quality() == {"linhas_staging": 6, "linhas_tratadas": 3}


def test_fixed_queries_are_read_only_selects():
    queries = (supabase.SELECT_DAILY, supabase.SELECT_MONTHLY, supabase.SELECT_QUALITY)
    assert all(query.lstrip().upper().startswith("SELECT") for query in queries)


def test_publish_replaces_marts_enables_rls_and_uses_native_types(fake_db, tmp_path):
    daily = make_daily(*[day("2026-11-10", None, 5), day("2026-11-11", "SP", 7)])
    audit = AuditLogger(tmp_path / "audit.jsonl")

    supabase.publish_marts(daily, monthly_summary(), {"linhas_staging": 6}, audit)

    statements = "\n".join(fake_db.statements)
    assert "CREATE SCHEMA IF NOT EXISTS srag" in statements
    assert statements.count("ENABLE ROW LEVEL SECURITY") == 3
    for table in ("mart_daily_summary", "mart_monthly_summary", "quality_report"):
        assert f"TRUNCATE srag.{table}" in statements
    daily_rows = next(rows for sql, rows in fake_db.copied.items() if "mart_daily_summary" in sql)
    assert daily_rows[0][:2] == (date(2026, 11, 10), None)  # data nativa e NaN -> None
    assert type(daily_rows[1][2]) is int
    log = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert '"database_publish"' in log and "postgresql://" not in log
