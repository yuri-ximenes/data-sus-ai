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


def arrow(ax, start, end, label="", rad=0.0, label_offset=(0.0, 0.12)):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "->", "color": "#333", "connectionstyle": f"arc3,rad={rad}"},
    )
    if label:
        ax.text(
            (start[0] + end[0]) / 2 + label_offset[0],
            (start[1] + end[1]) / 2 + label_offset[1],
            label,
            fontsize=7,
            ha="center",
            color="#333",
        )


fig, ax = plt.subplots(figsize=(14, 7.8))
ax.set_xlim(0, 14)
ax.set_ylim(0, 7.8)
ax.axis("off")
ax.set_title("SRAG Report Agent - Arquitetura conceitual", fontsize=14, weight="bold")

# Fluxo principal: pedido -> guardrail -> orquestrador <-> LLM
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
box(ax, 9.0, 5.6, 2.2, 0.9, "LLM (configurável)\nOpenAI (padrão) / Claude\nGemini / Groq", "ext")

# Ferramentas do agente
TOOL_W = 2.45
box(ax, 0.2, 1.7, TOOL_W, 1.0, "Tool: get_srag_metrics\n5 métricas", "tool")
box(ax, 2.8, 1.7, TOOL_W, 1.0, "Tool: get_srag_breakdowns\nUF + agente etiológico", "tool")
box(ax, 5.4, 1.7, TOOL_W, 1.0, "Tool: generate_srag_charts\ndiário 30d / mensal 12m", "tool")
box(ax, 8.0, 1.7, TOOL_W, 1.0, "Tool: search_srag_news\nnotícias sanitizadas", "tool")

# Fontes de dados
box(
    ax,
    1.9,
    0.3,
    4.2,
    0.8,
    "Banco de dados: marts Parquet (agregados)\nstaging CSV → tratamento → marts",
    "ext",
)
box(ax, 8.0, 0.3, TOOL_W, 0.8, "Google News RSS\n(tempo real)", "ext")

# Saída e governança
box(ax, 11.6, 5.6, 2.2, 0.9, "Auditoria JSONL\nhash encadeado", "guard")
box(ax, 11.6, 4.0, 2.2, 0.9, "Guardrail de saída\nsem PII, números ancorados", "guard")
box(ax, 11.6, 1.7, 2.2, 1.0, "Relatório Markdown\nmétricas + gráficos\n+ análise + fontes", "out")

arrow(ax, (2.1, 6.05), (2.6, 6.05), "pedido")
arrow(ax, (4.8, 6.05), (5.4, 6.05))
arrow(ax, (8.2, 6.25), (9.0, 6.25), "prompt")
arrow(ax, (9.0, 5.85), (8.2, 5.85), "tool calls", label_offset=(0.0, -0.3))

# Orquestrador chama as 4 tools
arrow(ax, (5.7, 5.3), (1.4, 2.7), "chama", label_offset=(-0.6, 0.0))
arrow(ax, (6.2, 5.3), (4.0, 2.7))
arrow(ax, (6.8, 5.3), (6.6, 2.7))
arrow(ax, (7.6, 5.3), (9.2, 2.7))

# Tools -> fontes de dados
arrow(ax, (1.4, 1.7), (2.6, 1.1))
arrow(ax, (4.0, 1.7), (3.8, 1.1))
arrow(ax, (6.6, 1.7), (5.0, 1.1))
arrow(ax, (9.2, 1.7), (9.2, 1.1))

# Saída: análise -> guardrail -> relatório; auditoria registra tudo
arrow(ax, (8.2, 5.5), (11.6, 4.6), "análise", label_offset=(0.0, 0.15))
arrow(ax, (12.7, 4.0), (12.7, 2.7), "aprovada", label_offset=(0.5, 0.0))
arrow(
    ax,
    (7.0, 6.8),
    (11.6, 6.4),
    "registra decisões, tools e guardrails",
    rad=-0.3,
    label_offset=(0.0, 0.55),
)

fig.savefig(OUTPUT, format="pdf", bbox_inches="tight")
print(f"Gerado {OUTPUT}")
