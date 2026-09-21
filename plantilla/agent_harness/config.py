"""Configuración central: todo lo ajustable vive aquí y se lee del entorno (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Mapping


def _num(env: Mapping[str, str], clave: str, defecto, tipo):
    valor = env.get(clave)
    return defecto if valor in (None, "") else tipo(valor)


@dataclass(frozen=True)
class Settings:
    # --- modelo y cliente
    modelo: str = "claude-sonnet-5"
    api_key: str | None = None
    workspace_id: str | None = None
    max_retries: int = 3
    timeout: float = 20.0
    max_tokens_agente: int = 1024
    # --- límites del harness
    presupuesto_tokens: int = 12000  # por conversación (hilo); ajústalo con la API real
    max_traspasos: int = 2  # por mensaje del usuario
    ventana_mensajes: int = 40  # mensajes que se ENVÍAN al modelo (el hilo guarda todo)
    recursion_limit: int = 25
    max_chars_resultado: int = 4000  # tope de un resultado de tool que entra al contexto
    # --- resiliencia de tools
    breaker_umbral: int = 3
    breaker_enfriamiento: float = 30.0
    # --- persistencia y logs
    checkpoint_db: str = ":memory:"  # ":memory:" (volátil) o ruta a un archivo SQLite
    log_level: str = "WARNING"  # en producción: AGENT_LOG_LEVEL=INFO (un JSON por evento)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        d = cls()
        return cls(
            modelo=env.get("AGENT_MODEL", d.modelo),
            api_key=env.get("ANTHROPIC_API_KEY"),
            workspace_id=env.get("ANTHROPIC_WORKSPACE_ID"),
            max_retries=_num(env, "AGENT_MAX_RETRIES", d.max_retries, int),
            timeout=_num(env, "AGENT_TIMEOUT", d.timeout, float),
            max_tokens_agente=_num(env, "AGENT_MAX_TOKENS", d.max_tokens_agente, int),
            presupuesto_tokens=_num(env, "AGENT_PRESUPUESTO_TOKENS", d.presupuesto_tokens, int),
            max_traspasos=_num(env, "AGENT_MAX_TRASPASOS", d.max_traspasos, int),
            ventana_mensajes=_num(env, "AGENT_VENTANA_MENSAJES", d.ventana_mensajes, int),
            recursion_limit=_num(env, "AGENT_RECURSION_LIMIT", d.recursion_limit, int),
            max_chars_resultado=_num(env, "AGENT_MAX_CHARS_RESULTADO", d.max_chars_resultado, int),
            breaker_umbral=_num(env, "AGENT_BREAKER_UMBRAL", d.breaker_umbral, int),
            breaker_enfriamiento=_num(env, "AGENT_BREAKER_ENFRIAMIENTO", d.breaker_enfriamiento, float),
            checkpoint_db=env.get("AGENT_CHECKPOINT_DB", d.checkpoint_db),
            log_level=env.get("AGENT_LOG_LEVEL", d.log_level),
        )

    def con(self, **cambios) -> "Settings":
        """Copia con cambios (los tests y los evals inyectan fallas así, sin monkeypatch)."""
        return replace(self, **cambios)
