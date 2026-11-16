"""Guardrails de entrada, de conteúdo externo (notícias) e de saída do LLM, e redação de PII."""

import re
from dataclasses import dataclass, field

MAX_REQUEST_LENGTH = 1000
NUMBER_TOLERANCE = 0.15

PII_PATTERNS = {
    "cpf": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "telefone": re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}-\d{4}\b"),
}
INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignor[ea]\w*\s+(todas?\s+)?(as\s+)?(instru|regras|anterior)",
        r"ignore\s+(all\s+)?(previous|prior|above)",
        r"desconsidere\s+(as\s+)?(instru|regras)",
        r"(system|developer)\s+prompt",
        r"prompt\s+do\s+sistema",
        r"voc[eê]\s+agora\s+[eé]",
        r"you\s+are\s+now",
        r"revele\s+.*(chave|senha|prompt)",
    )
]
TOPIC_KEYWORDS = (
    "srag",
    "síndrome",
    "sindrome",
    "respirat",
    "relatório",
    "relatorio",
    "surto",
    "casos",
    "métrica",
    "metrica",
    "uti",
    "mortalidade",
    "vacina",
    "internaç",
    "internac",
    "influenza",
    "covid",
)
URL_PATTERN = re.compile(r"https?://[^\s)\]>]+")
PERCENT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


@dataclass
class GuardrailResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Substitui padrões de PII por marcadores e devolve os tipos encontrados."""
    found = []
    for kind, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            found.append(kind)
            text = pattern.sub(f"[{kind.upper()} REMOVIDO]", text)
    return text, found


def has_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in INJECTION_PATTERNS)


def check_user_request(text: str) -> GuardrailResult:
    reasons = []
    if not text.strip() or len(text) > MAX_REQUEST_LENGTH:
        reasons.append(f"pedido vazio ou acima de {MAX_REQUEST_LENGTH} caracteres")
    if has_injection(text):
        reasons.append("possível tentativa de prompt injection")
    if redact_pii(text)[1]:
        reasons.append("o pedido contém dados pessoais (CPF, e-mail ou telefone)")
    if not any(keyword in text.lower() for keyword in TOPIC_KEYWORDS):
        reasons.append("pedido fora do escopo (relatório de SRAG)")
    return GuardrailResult(not reasons, reasons)


def sanitize_untrusted_text(text: str, max_length: int = 300) -> str | None:
    """Limpa texto externo (notícias). Retorna None se parecer instrução ao modelo."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean or has_injection(clean):
        return None
    clean, _ = redact_pii(clean)
    return clean[:max_length]


def _numbers(text: str) -> list[float]:
    return [float(m.replace(",", ".")) for m in PERCENT_PATTERN.findall(text)]


def check_narrative(
    text: str, metric_values: list[float], allowed_urls: set[str]
) -> GuardrailResult:
    """Valida a análise do LLM: sem PII, percentuais ancorados nas métricas e URLs conhecidas."""
    reasons = []
    if not text.strip():
        reasons.append("análise vazia")
    if redact_pii(text)[1]:
        reasons.append("a análise contém dados pessoais")
    allowed = [abs(v) for v in metric_values]
    for number in _numbers(text):
        if not any(abs(abs(number) - value) <= NUMBER_TOLERANCE for value in allowed):
            reasons.append(f"percentual {number}% não corresponde a nenhuma métrica calculada")
    for url in URL_PATTERN.findall(text):
        if url.rstrip(".,") not in allowed_urls:
            reasons.append(f"URL não proveniente das ferramentas: {url}")
    return GuardrailResult(not reasons, reasons)
