"""Raíz de composición: aquí (y solo aquí) se decide QUÉ piezas concretas se ensamblan."""

from __future__ import annotations

from dataclasses import dataclass

from .agents.soporte import AGENTES_SOPORTE, CONTEXTO_SOPORTE
from .config import Settings
from .graph import Orquestador
from .llm import LLM, AnthropicLLM
from .memory.usuario import MemoriaUsuario
from .tools.soporte import SoporteBackend, crear_tools_soporte


@dataclass
class App:
    orquestador: Orquestador
    backend: SoporteBackend
    memoria_usuario: MemoriaUsuario


def crear_app(settings: Settings | None = None, llm: LLM | None = None, checkpointer=None) -> App:
    settings = settings or Settings.from_env()
    backend = SoporteBackend()
    memoria = MemoriaUsuario()
    orq = Orquestador(
        settings, llm or AnthropicLLM(settings), crear_tools_soporte(backend), AGENTES_SOPORTE,
        contexto=CONTEXTO_SOPORTE, checkpointer=checkpointer, memoria_usuario=memoria,
    )
    return App(orq, backend, memoria)
