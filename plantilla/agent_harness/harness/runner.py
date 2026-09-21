"""ToolRunner: ÚNICA puerta por la que se ejecuta una tool. Aplica, en orden:

  1. tool conocida        2. argumentos válidos      3. aprobación humana (si es sensible)
  4. idempotencia         5. circuit breaker         6. métricas        7. resultado como DATOS

Siempre devuelve un bloque `tool_result` (nunca lanza): un tool_use sin su tool_result rompe el hilo.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable

from ..config import Settings
from ..observability import evento
from ..tools import ToolRegistry
from .safety import CircuitBreaker, EjecutorIdempotente, Metricas, sanitizar


class ToolRunner:
    def __init__(self, registry: ToolRegistry, settings: Settings, reloj: Callable[[], float] = time.monotonic):
        self.registry, self.settings, self.reloj = registry, settings, reloj
        self.metricas = Metricas()
        self.idempotencia = EjecutorIdempotente()
        self.breakers: dict[str, CircuitBreaker] = {}

    def _resultado(self, bloque: dict, contenido: str, error: bool = False) -> dict:
        r = {"type": "tool_result", "tool_use_id": bloque["id"], "content": contenido}
        if error:
            r["is_error"] = True
        return r

    def ejecutar(self, bloque: dict, aprobado: bool) -> dict:
        nombre, args = bloque["name"], bloque["input"]
        tool = self.registry.get(nombre)
        if tool is None:
            return self._resultado(bloque, f"La herramienta '{nombre}' no existe.", True)
        error = tool.validar_args(args)
        if error:
            evento("tool.invalida", logging.WARNING, tool=nombre, error=error)
            return self._resultado(bloque, error, True)
        if tool.sensible and not aprobado:
            evento("tool.rechazada", logging.WARNING, tool=nombre)
            return self._resultado(bloque, "Acción rechazada por un supervisor humano. No se ejecutó.", True)

        breaker = self.breakers.setdefault(
            nombre, CircuitBreaker(self.settings.breaker_umbral, self.settings.breaker_enfriamiento, self.reloj)
        )
        clave = tool.clave_idempotencia(args) if tool.clave_idempotencia else None
        if clave is not None and clave in self.idempotencia.resultados:
            evento("tool.repetida", tool=nombre)
            return self._resultado(bloque, self._formatear(self.idempotencia.ejecutar(clave, lambda: None)))
        if not breaker.permitir():
            evento("tool.circuito_abierto", logging.WARNING, tool=nombre)
            return self._resultado(bloque, f"{nombre} está temporalmente fuera de servicio; no reintentes ahora.", True)

        inicio = self.reloj()
        try:
            llamar = lambda: tool.funcion(**args)  # noqa: E731
            resultado = self.idempotencia.ejecutar(clave, llamar) if clave is not None else llamar()
        except Exception as e:  # una tool nunca debe tumbar el grafo
            self.metricas.registrar(nombre, self.reloj() - inicio, ok=False)
            breaker.fallo()
            evento("tool.fallo", logging.ERROR, tool=nombre, error=f"{type(e).__name__}: {e}")
            return self._resultado(bloque, sanitizar(f"La herramienta falló: {e}. No se pudo completar la acción.", self.settings.max_chars_resultado), True)
        segundos = self.reloj() - inicio
        self.metricas.registrar(nombre, segundos, ok=True)
        breaker.exito()
        evento("tool.ok", tool=nombre, segundos=round(segundos, 4))
        return self._resultado(bloque, self._formatear(resultado))

    def _formatear(self, resultado) -> str:
        crudo = resultado if isinstance(resultado, str) else json.dumps(resultado, ensure_ascii=False, default=str)
        return sanitizar(crudo, self.settings.max_chars_resultado)
