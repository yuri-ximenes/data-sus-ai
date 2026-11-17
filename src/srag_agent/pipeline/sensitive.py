"""Guarda de dados sensíveis: nenhuma camada pode referenciar colunas identificadoras."""

import re

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


def assert_no_sensitive_columns(sql: str, source: str) -> None:
    """Falha se o SQL mencionar qualquer coluna sensível (executado antes de cada camada)."""
    found = sorted(
        column
        for column in SENSITIVE_COLUMNS
        if re.search(rf"\b{column}\b", sql, flags=re.IGNORECASE)
    )
    if found:
        raise PermissionError(f"{source} referencia colunas sensíveis: {', '.join(found)}")
