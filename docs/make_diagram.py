"""Gera docs/arquitetura.pdf (diagrama conceitual). Uso: uv run python docs/make_diagram.py"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

OUTPUT = Path(__file__).parent / "arquitetura.pdf"
COLORS = {
    "user": "#e8eef2",
    "guard": "#fde8d0",
    "agent": "#cfe5f0",
    "tool": "#dff0d8",
    "ext": "#eee0f5",
    "out": "#f5f0c8",
}


def box(ax, x, y, w, h, text, kind):
    ax.add_patch(
        FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fc=COLORS[kind], ec="#444", lw=1.2)
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5)


def arrow(ax, start, end, label=""):
    ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "color": "#333"})
    if label:
        ax.text(
            (start[0] + end[0]) / 2,
            (start[1] + end[1]) / 2 + 0.12,
            label,
            fontsize=7,
            ha="center",
            color="#333",
        )


fig, ax = plt.subplots(figsize=(13, 7.5))
ax.set_xlim(0, 13)
ax.set_ylim(0, 7.5)
ax.axis("off")
ax.set_title("SRAG Report Agent - Arquitetura conceitual", fontsize=14, weight="bold")

box(ax, 0.2, 5.6, 1.9, 0.9, "Profissional\nde saúde", "user")
box(ax, 2.6, 5.6, 2.2, 0.9, "Guardrail de entrada\nescopo, injection, PII", "guard")
box(
    ax,
    5.4,
    5.3,
    2.8,
    1.5,
    "AGENTE PRINCIPAL\n(Orquestrador LangGraph)\ndecide quais tools chamar",
    "agent",
)
box(ax, 9.0, 5.6, 2.0, 0.9, "LLM (configurável)\nGroq / Gemini / Claude", "ext")
box(ax, 5.4, 3.7, 2.8, 0.9, "Guardrail de saída\nsem PII, números ancorados", "guard")

box(ax, 0.4, 1.7, 2.8, 1.0, "Tool: get_srag_metrics\n4 métricas", "tool")
box(ax, 3.6, 1.7, 2.8, 1.0, "Tool: generate_srag_charts\ndiário 30d / mensal 12m", "tool")
box(ax, 6.8, 1.7, 2.8, 1.0, "Tool: search_srag_news\nnotícias sanitizadas", "tool")
box(ax, 0.4, 0.3, 2.8, 0.8, "DuckDB + CSV Open DATASUS\n(6 colunas, sem PII)", "ext")
box(ax, 6.8, 0.3, 2.8, 0.8, "Google News RSS\n(tempo real)", "ext")
box(ax, 10.2, 1.7, 2.6, 1.0, "Relatório Markdown\nmétricas + gráficos\n+ análise + fontes", "out")
box(ax, 10.2, 3.7, 2.6, 0.9, "Auditoria JSONL\nhash encadeado", "guard")

arrow(ax, (2.1, 6.05), (2.6, 6.05), "pedido")
arrow(ax, (4.8, 6.05), (5.4, 6.05))
arrow(ax, (8.2, 6.2), (9.0, 6.2), "prompt")
arrow(ax, (9.0, 5.8), (8.2, 5.8), "tool calls")
arrow(ax, (6.0, 5.3), (2.0, 2.7), "chama")
arrow(ax, (6.8, 5.3), (5.0, 2.7))
arrow(ax, (7.6, 5.3), (8.2, 2.7))
arrow(ax, (1.8, 1.7), (1.8, 1.1))
arrow(ax, (8.2, 1.7), (8.2, 1.1))
arrow(ax, (6.8, 5.3), (6.8, 4.6), "análise")
arrow(ax, (8.2, 4.15), (10.2, 2.7), "aprovada")
arrow(ax, (8.2, 5.5), (10.6, 4.6), "registra decisões e tools")

fig.savefig(OUTPUT, format="pdf", bbox_inches="tight")
print(f"Gerado {OUTPUT}")
