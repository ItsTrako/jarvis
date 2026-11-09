"""Proveedores de modelos de lenguaje: Claude (nube) y Ollama (local y gratuito)."""

from __future__ import annotations

from .base import LLMProvider, TurnResult


def active_provider_name() -> str:
    """Proveedor efectivo. En modo 'auto' se usa Claude si hay API key y, si no, el modelo local."""
    from ..config import get_config
    from ..secrets import has_secret

    name = get_config().llm.provider
    if name == "auto":
        return "anthropic" if has_secret("anthropic_api_key") else "ollama"
    return name


def get_provider() -> LLMProvider:
    name = active_provider_name()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider.instance()
    if name == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider.instance()
    raise ValueError(f"Proveedor no soportado: {name}")


def is_local() -> bool:
    return active_provider_name() == "ollama"


__all__ = ["LLMProvider", "TurnResult", "get_provider", "active_provider_name", "is_local"]
