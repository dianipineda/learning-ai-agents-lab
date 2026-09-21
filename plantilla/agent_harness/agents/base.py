from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    """Un agente = nombre + descripción (la lee el supervisor) + prompt + nombres de sus tools.

    Agregar un agente es escribir un AgentSpec y pasarlo a `Orquestador`; el grafo no cambia.
    """

    name: str
    description: str  # cuándo debe atender este agente (el supervisor decide con esto)
    system: str
    tools: tuple[str, ...] = ()


def prompt_supervisor(agentes: list[AgentSpec], contexto: str = "") -> str:
    lista = "\n".join(f"- {a.name}: {a.description}" for a in agentes)
    return (
        f"Eres el supervisor de un equipo de agentes. {contexto}\n"
        f"Lee el mensaje nuevo del usuario y elige qué agente debe atenderlo:\n{lista}\n"
        "Se te indica qué agente venía atendiendo la conversación. Si el mensaje es un seguimiento "
        "(por ejemplo, solo trae un dato que faltaba), conserva ese agente.\n"
        "Usa siempre la herramienta elegir_agente."
    ).strip()
