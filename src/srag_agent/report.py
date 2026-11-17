"""Montagem do relatório final. Números e tabelas vêm do código; o LLM escreve só a análise."""

import hashlib
from pathlib import Path

import pandas as pd

from srag_agent.metrics import MIN_CASES_FOR_GROWTH
from srag_agent.tools import ToolContext

NO_NARRATIVE = "_Análise do LLM indisponível (modo sem LLM ou bloqueada pelos guardrails)._"

QUALITY_LABELS = {
    "linhas_staging": "Linhas lidas do CSV (staging)",
    "descartadas_data_invalida": "Descartadas: data de notificação ausente, pré-2019 ou futura",
    "descartadas_duplicadas": "Descartadas: notificações duplicadas",
    "linhas_tratadas": "Linhas válidas após o tratamento",
    "hospital_inferido_por_uti": "Internação inferida pela passagem por UTI",
    "uf_invalida_para_nula": "UF inválida convertida para nulo",
    "hospital_ignorado_para_nulo": "Internação com código ignorado (9) convertida para nulo",
    "uti_ignorado_para_nulo": "UTI com código ignorado (9) convertida para nulo",
    "evolucao_ignorada_para_nulo": "Evolução com código ignorado (9) convertida para nulo",
    "vacina_ignorada_para_nulo": "Vacina COVID com código ignorado (9) convertida para nulo",
    "ausentes_uf": "Casos sem UF (entram no total nacional, não nos filtros por UF)",
    "classi_fin_ignorada_para_nulo": "Classificação final fora do domínio convertida para nulo",
    "ausentes_classi_fin": "Casos sem classificação final (fora da composição por agente)",
    "ausentes_uti": "Casos sem informação de UTI (excluídos do denominador)",
    "ausentes_evolucao": "Casos sem desfecho (excluídos do denominador da mortalidade)",
    "ausentes_vacina_cov": "Casos sem informação vacinal (excluídos do denominador)",
}


def _format_count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_value(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.1f}%".replace(".", ",")


def _uf_table(table: pd.DataFrame) -> str:
    rows = "\n".join(
        f"| {row.uf} | {_format_count(row.casos)} | {_format_count(row.casos_anteriores)} | "
        f"{_format_value(None if pd.isna(row.variacao_pct) else row.variacao_pct)} |"
        for row in table.itertuples()
    )
    return f"| UF | Casos | Casos no período anterior | Variação |\n|---|---|---|---|\n{rows}"


def _breakdown_sections(ctx: ToolContext) -> str:
    """Seções de UF (só visão nacional) e de agente etiológico, calculadas pelo código."""
    sections = []
    if ctx.uf_top_cases is not None and ctx.uf_top_growth is not None:
        sections.append(
            "## Panorama por UF\n\n"
            f"**UFs com mais casos** (últimos {ctx.settings.window_days} dias):\n\n"
            f"{_uf_table(ctx.uf_top_cases)}\n\n"
            f"**UFs com maior crescimento** (mínimo de {MIN_CASES_FOR_GROWTH} casos no período):"
            f"\n\n{_uf_table(ctx.uf_top_growth)}"
        )
    if ctx.etiology is not None:
        rows = "\n".join(
            f"| {row.agente} | {_format_count(row.casos)} | {_format_value(row.percentual)} |"
            for row in ctx.etiology.table.itertuples()
        )
        sections.append(
            "## Agente etiológico\n\n"
            "| Agente | Casos | % dos classificados |\n|---|---|---|\n"
            f"{rows}\n\n"
            f"Casos classificados: {_format_count(ctx.etiology.classified)}. Ainda sem "
            f"classificação final (em geral os mais recentes): "
            f"{_format_count(ctx.etiology.unclassified)}."
        )
    return "\n\n".join(sections)


def build_report(ctx: ToolContext, narrative: str, quality: dict[str, int]) -> str:
    scope = ctx.uf or "Brasil"
    rows = "\n".join(
        f"| {m.name} | {_format_value(m.value)} | "
        f"{_format_count(m.numerator)} / {_format_count(m.denominator)} | "
        f"{m.description} |"
        for m in ctx.metrics
    )
    charts = "\n\n".join(f"![{p.stem}]({p.name})" for p in ctx.chart_paths)
    news = (
        "\n".join(f"- [{n.title}]({n.url}) - {n.source}, {n.published}" for n in ctx.news)
        or "_Nenhuma notícia recuperada._"
    )
    quality_rows = "\n".join(
        f"| {label} | {_format_count(quality[key])} |"
        for key, label in QUALITY_LABELS.items()
        if key in quality
    )
    return f"""# Relatório de SRAG - {scope}

Data de referência: **{ctx.as_of.isoformat()}** (janela de {ctx.settings.window_days} dias).

## Métricas

| Métrica | Valor | Numerador / Denominador | Definição |
|---|---|---|---|
{rows}

{_breakdown_sections(ctx)}

## Gráficos

{charts}

{narrative or NO_NARRATIVE}

## Fontes de notícias

{news}

## Qualidade dos dados (tratamento staging → marts)

| Etapa de tratamento | Linhas |
|---|---|
{quality_rows}

> Dados agregados do Open DATASUS (SIVEP-Gripe); casos recentes sofrem atraso de notificação.
> Relatório de apoio à decisão, não substitui avaliação epidemiológica profissional.
"""


def save_report(ctx: ToolContext, content: str) -> Path:
    ctx.settings.output_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.settings.output_dir / f"relatorio_{ctx.as_of}.md"
    path.write_text(content, encoding="utf-8")
    ctx.audit.log(
        "report_generated",
        file=path.name,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    return path
