"""Busca de notícias recentes sobre SRAG via Google News RSS (sem chave de API)."""

from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import httpx
from defusedxml import ElementTree

from srag_agent.guardrails import sanitize_untrusted_text

RSS_URL = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
BASE_QUERY = '("síndrome respiratória aguda grave" OR SRAG)'
REQUEST_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_query(extra_terms: str, max_age_days: int) -> str:
    terms = f"{BASE_QUERY} {extra_terms}".strip()
    return quote_plus(f"{terms} when:{max_age_days}d")


def parse_feed(xml_text: str, max_items: int) -> list[NewsItem]:
    """Converte o RSS em itens, descartando entradas suspeitas (prompt injection)."""
    items: list[NewsItem] = []
    for node in ElementTree.fromstring(xml_text).iter("item"):
        title = sanitize_untrusted_text(node.findtext("title", ""))
        url = (node.findtext("link") or "").strip()
        if title is None or not url.startswith("https://"):
            continue
        source = sanitize_untrusted_text(node.findtext("source", ""), 80) or "desconhecida"
        try:
            published = parsedate_to_datetime(node.findtext("pubDate", "")).date().isoformat()
        except (TypeError, ValueError):
            published = "data desconhecida"
        items.append(NewsItem(title, source, published, url))
        if len(items) >= max_items:
            break
    return items


def fetch_news(extra_terms: str, max_items: int, max_age_days: int) -> list[NewsItem]:
    url = RSS_URL.format(query=build_query(extra_terms, max_age_days))
    response = httpx.get(url, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    return parse_feed(response.text, max_items)
