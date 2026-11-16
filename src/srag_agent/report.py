"""Montagem do relatório final. Números e tabelas vêm do código; o LLM escreve só a análise."""

import hashlib
from pathlib import Path

from srag_agent.tools import ToolContext

NO_NARRATIVE = "_Análise do LLM indisponível (modo sem LLM ou bloqueada pelos guardrails)._"


def _format_value(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.1f}%".replace(".", ",")


def build_report(ctx: ToolContext, narrative: str, quality: dict[str, int]) -> str:
    scope = ctx.uf or "Brasil"
    rows = "\n".join(
        f"| {m.name} | {_format_value(m.value)} | {m.numerator} / {m.denominator} | "
        f"{m.description} |"
        for m in ctx.metrics
    )
    charts = "\n\n".join(f"![{p.stem}]({p.name})" for p in ctx.chart_paths)
    news = (
        "\n".join(f"- [{n.title}]({n.url}) - {n.source}, {n.published}" for n in ctx.news)
        or "_Nenhuma notícia recuperada._"
    )
    quality_lines = "\n".join(
        f"- {key.replace('_', ' ')}: {value}" for key, value in quality.items()
    )
    return f"""# Relatório de SRAG - {scope}

Data de referência: **{ctx.as_of.isoformat()}** (janela de {ctx.settings.window_days} dias).

## Métricas

| Métrica | Valor | Numerador / Denominador | Definição |
|---|---|---|---|
{rows}

## Gráficos

{charts}

{narrative or NO_NARRATIVE}

## Fontes de notícias

{news}

## Qualidade dos dados

{quality_lines}

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
