"""Guardrails deterministas (código, no prompts): lo que NUNCA debe depender de que el modelo obedezca."""

from __future__ import annotations

from ..config import Settings
from ..tools import ToolRegistry

TRANSFERIR = "transferir_a"


def es_traspaso(bloque: dict) -> bool:
    return bloque["type"] == "tool_use" and bloque["name"] == TRANSFERIR


def hay_traspaso(mensaje: dict) -> bool:
    return any(es_traspaso(b) for b in mensaje["content"])


def presupuesto_excedido(estado: dict, settings: Settings) -> bool:
    return estado.get("tokens_usados", 0) > settings.presupuesto_tokens


def requiere_aprobacion(registry: ToolRegistry, bloque: dict) -> bool:
    """Aprobación humana solo si la tool es sensible Y sus argumentos son válidos (no se molesta
    al humano por una llamada que se va a rechazar igual)."""
    if bloque["type"] != "tool_use":
        return False
    tool = registry.get(bloque["name"])
    return tool is not None and tool.sensible and tool.validar_args(bloque["input"]) is None


def hay_que_aprobar(registry: ToolRegistry, mensaje: dict) -> bool:
    return any(requiere_aprobacion(registry, b) for b in mensaje["content"])
