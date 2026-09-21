"""Único punto de contacto con la API del modelo.

El resto del harness solo conoce `LLM` (un Protocol) y `Respuesta`: así se puede sustituir por un
doble de prueba (`agent_harness.testing.FakeLLM`) o por otro proveedor sin tocar el grafo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import Settings


class LLMError(Exception):
    """Falla de la API (red, timeout, límite de tasa, 5xx…), ya agotados los reintentos del cliente."""


@dataclass
class Respuesta:
    content: list[dict]  # bloques como dicts simples: serializables por el checkpointer
    stop_reason: str
    tokens: int  # entrada + salida de ESTA llamada

    @property
    def texto(self) -> str:
        return next((b["text"] for b in self.content if b["type"] == "text"), "")


class LLM(Protocol):
    def crear(self, *, system: str, messages: list[dict], tools: list[dict],
              max_tokens: int, tool_choice: dict | None = None) -> Respuesta: ...


class AnthropicLLM:
    def __init__(self, settings: Settings, cliente=None):
        import anthropic

        self._anthropic = anthropic
        self.settings = settings
        if cliente is None:
            headers = {"anthropic-workspace-id": settings.workspace_id} if settings.workspace_id else {}
            cliente = anthropic.Anthropic(
                api_key=settings.api_key,
                default_headers=headers,
                max_retries=settings.max_retries,
                timeout=settings.timeout,
            )
        self.cliente = cliente

    def crear(self, *, system, messages, tools, max_tokens, tool_choice=None) -> Respuesta:
        args = {"model": self.settings.modelo, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            args["tools"] = tools
        if tool_choice:
            args["tool_choice"] = tool_choice
        try:
            r = self.cliente.messages.create(**args)
        except self._anthropic.APIError as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
        return Respuesta(
            content=_bloques(r.content),
            stop_reason=r.stop_reason,
            tokens=r.usage.input_tokens + r.usage.output_tokens,
        )


def _bloques(content) -> list[dict]:
    salida = []
    for b in content:
        if b.type == "text":
            salida.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            salida.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return salida
