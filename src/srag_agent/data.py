"""Carga e tratamento dos dados de SRAG (Open DATASUS).

Princípio de minimização: apenas as colunas estritamente necessárias para as métricas
são lidas do CSV. Colunas identificadoras (CPF, nome, endereço etc.) nunca são carregadas.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from srag_agent.config import VALID_UFS

# Colunas usadas pelo relatório (nome no CSV -> nome interno).
USED_COLUMNS = {
    "DT_NOTIFIC": "dt_notific",
    "SG_UF_NOT": "uf",
    "HOSPITAL": "hospital",
    "UTI": "uti",
    "EVOLUCAO": "evolucao",
    "VACINA_COV": "vacina_cov",
}

# Colunas que identificam (ou ajudam a reidentificar) o paciente. Jamais devem ser lidas.
SENSITIVE_COLUMNS = frozenset(
    {
        "NU_CPF",
        "NU_CNS",
        "NM_PACIENT",
        "NM_MAE_PAC",
        "DT_NASC",
        "NM_BAIRRO",
        "NM_LOGRADO",
        "NU_NUMERO",
        "NM_COMPLEM",
        "NU_CEP",
        "NU_DDD_TEL",
        "NU_TELEFON",
        "NU_DO",
        "NM_RESPONSA",
    }
)

DATE_COLUMNS = ("DT_NOTIFIC",)
CATEGORICAL_DOMAINS = {
    "hospital": {1, 2},
    "uti": {1, 2},
    "evolucao": {1, 2, 3},
    "vacina_cov": {1, 2},
}
MIN_VALID_DATE = pd.Timestamp("2019-01-01")


@dataclass(frozen=True)
class CleanedData:
    frame: pd.DataFrame
    quality: dict[str, int]


def _select_clause() -> str:
    parts = []
    for source, target in USED_COLUMNS.items():
        if source in DATE_COLUMNS:
            parts.append(
                f"COALESCE(TRY_CAST(SUBSTR({source}, 1, 10) AS DATE), "
                f"CAST(TRY_STRPTIME({source}, '%d/%m/%Y') AS DATE)) AS {target}"
            )
        elif target == "uf":
            parts.append(f"UPPER(TRIM({source})) AS {target}")
        else:
            parts.append(f"TRY_CAST({source} AS TINYINT) AS {target}")
    return ", ".join(parts)


def list_csv_files(raw_dir: Path) -> list[Path]:
    files = sorted(raw_dir.glob("INFLUD*.csv"))
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo INFLUD*.csv encontrado em {raw_dir}")
    return files


def load_raw(files: list[Path]) -> pd.DataFrame:
    """Lê apenas as colunas necessárias dos CSVs (separador ';')."""
    assert not SENSITIVE_COLUMNS & set(USED_COLUMNS), "Coluna sensível na lista de uso"
    sql = (
        f"SELECT {_select_clause()} FROM read_csv(?, delim=';', header=true, all_varchar=true, "
        "encoding='utf-8', ignore_errors=true, union_by_name=true)"
    )
    with duckdb.connect() as con:
        return con.execute(sql, [[str(f) for f in files]]).df()


def clean(raw: pd.DataFrame, today: pd.Timestamp | None = None) -> CleanedData:
    """Aplica regras de qualidade e devolve o dataframe tratado com contadores de descarte."""
    today = today or pd.Timestamp.today().normalize()
    frame = raw.copy()
    frame["dt_notific"] = pd.to_datetime(frame["dt_notific"])
    quality = {"linhas_lidas": len(frame)}

    missing_date = frame["dt_notific"].isna()
    out_of_range = ~missing_date & (
        (frame["dt_notific"] < MIN_VALID_DATE) | (frame["dt_notific"] > today)
    )
    quality["descartadas_sem_data"] = int(missing_date.sum())
    quality["descartadas_data_fora_do_intervalo"] = int(out_of_range.sum())
    frame = frame[~missing_date & ~out_of_range].copy()

    for column, domain in CATEGORICAL_DOMAINS.items():
        frame[column] = frame[column].where(frame[column].isin(domain)).astype("Int8")
    frame["uf"] = frame["uf"].where(frame["uf"].isin(VALID_UFS))

    quality["linhas_validas"] = len(frame)
    return CleanedData(frame=frame.reset_index(drop=True), quality=quality)


def load_cases(raw_dir: Path) -> CleanedData:
    return clean(load_raw(list_csv_files(raw_dir)))
