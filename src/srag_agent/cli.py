"""Interface de linha de comando: `uv run srag-report [--uf SP] [--no-llm]`."""

import argparse
import sys
from datetime import date

from dotenv import load_dotenv

from srag_agent.agent import run_agent
from srag_agent.audit import AuditLogger
from srag_agent.config import VALID_UFS, Settings
from srag_agent.pipeline import (
    build_marts,
    publish_marts,
    read_daily_summary,
    read_monthly_summary,
    read_quality,
)
from srag_agent.report import build_report, save_report
from srag_agent.tools import ToolContext, build_tools

DEFAULT_REQUEST = "Gere o relatório de SRAG com as métricas, gráficos e o contexto das notícias."


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relatório automatizado de SRAG")
    parser.add_argument("--uf", choices=sorted(VALID_UFS), help="Filtra por UF (padrão: Brasil)")
    parser.add_argument("--request", default=DEFAULT_REQUEST, help="Pedido em linguagem natural")
    parser.add_argument("--no-llm", action="store_true", help="Gera o relatório sem o agente LLM")
    parser.add_argument(
        "--publish-supabase",
        action="store_true",
        help="Refaz a pipeline (data/staging -> marts) e publica os marts no Supabase",
    )
    return parser.parse_args(argv)


def _publish_marts(settings: Settings, audit: AuditLogger) -> None:
    marts = build_marts(settings, audit)
    publish_marts(marts.daily, marts.monthly, marts.quality, audit)


def _run_without_llm(ctx: ToolContext, uf: str | None) -> str:
    """Executa as tools diretamente, sem LLM (útil para testes e sem chave de API)."""
    tools = {tool.name: tool for tool in build_tools(ctx)}
    tools["get_srag_metrics"].invoke({"uf": uf})
    tools["get_srag_breakdowns"].invoke({"uf": uf})
    tools["generate_srag_charts"].invoke({"uf": uf})
    tools["search_srag_news"].invoke({})
    return ""


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parse_args(argv)
    settings = Settings()
    audit = AuditLogger(settings.audit_log_path)
    audit.log("run_start", uf=args.uf, use_llm=not args.no_llm, request=args.request)

    try:
        if args.publish_supabase:
            _publish_marts(settings, audit)
        audit.log("data_source", backend="supabase")
        daily = read_daily_summary()
        monthly = read_monthly_summary()
        quality = read_quality()
    except (RuntimeError, FileNotFoundError) as error:  # configuração, CSVs ou conexão com o banco
        audit.log("run_error", error_type="DatabaseError", error=str(error)[:300])
        print(f"Erro de dados: {error}", file=sys.stderr)
        return 1
    as_of = min(daily["dt"].max().date(), date.today())
    ctx = ToolContext(settings, daily, monthly, as_of, audit, uf=args.uf)

    if args.no_llm:
        narrative = _run_without_llm(ctx, args.uf)
    else:
        try:
            state = run_agent(ctx, args.request)
        except Exception as error:  # falha do provedor de LLM (limite, indisponibilidade etc.)
            audit.log("run_error", error_type=type(error).__name__, error=str(error)[:500])
            print(
                f"Falha ao consultar o LLM ({type(error).__name__}). Tente novamente em alguns "
                "minutos ou troque SRAG_PROVIDER. Detalhes em logs/audit.jsonl.",
                file=sys.stderr,
            )
            return 1
        if state["blocked"]:
            audit.log("run_blocked", reason=state["messages"][-1].content)
            print("Execução bloqueada pelos guardrails. Veja logs/audit.jsonl.", file=sys.stderr)
            return 2
        narrative = state["narrative"]

    path = save_report(ctx, build_report(ctx, narrative, quality))
    audit.log("run_end", report=path.name)
    print(f"Relatório salvo em {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
