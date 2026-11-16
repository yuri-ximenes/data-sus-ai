"""Fábrica do modelo de linguagem. Provedor padrão: Gemini (free tier); alternativa: Claude."""

import os

from langchain_core.language_models.chat_models import BaseChatModel

from srag_agent.config import Settings

DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-3.8-flash",
    "anthropic": "claude-sonnet-5-5",
}
API_KEY_VARIABLES = {
    "groq": "GROQ_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def resolve_model_name(settings: Settings) -> str:
    return settings.model_name or DEFAULT_MODELS[settings.provider]


def create_llm(settings: Settings) -> BaseChatModel:
    """Cria o chat model do provedor configurado, exigindo a chave de API no ambiente."""
    provider = settings.provider
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Provedor inválido: {provider}. Use: {', '.join(DEFAULT_MODELS)}")
    key_variable = API_KEY_VARIABLES[provider]
    if not os.getenv(key_variable):
        raise RuntimeError(
            f"Variável {key_variable} ausente. Copie env.example para .env e preencha a chave."
        )
    model = resolve_model_name(settings)
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, temperature=0, max_retries=3)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, temperature=0, max_retries=3)
    from langchain_anthropic import ChatAnthropic

    # Modelos Claude 5 não aceitam temperature fora do padrão.
    return ChatAnthropic(model=model, max_tokens=2500)
