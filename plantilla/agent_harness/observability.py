"""Observabilidad: logs estructurados (una línea JSON por evento) correlacionados por thread_id."""

from __future__ import annotations

import contextvars
import json
import logging
import time

logger = logging.getLogger("agent_harness")
logger.addHandler(logging.NullHandler())  # librería: en silencio hasta que la app llame configurar_logging
_thread_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("thread_id", default=None)


def fijar_thread(thread_id: str | None):
    return _thread_id.set(thread_id)


def restaurar_thread(token) -> None:
    _thread_id.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        datos = {"ts": round(time.time(), 3), "nivel": record.levelname, "evento": record.getMessage()}
        datos.update(getattr(record, "campos", {}))
        return json.dumps(datos, ensure_ascii=False, default=str)


def configurar_logging(nivel: str = "INFO") -> None:
    if any(getattr(h, "_agent_harness", False) for h in logger.handlers):
        logger.setLevel(nivel)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._agent_harness = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(nivel)
    logger.propagate = False


def evento(nombre: str, nivel: int = logging.INFO, **campos) -> None:
    """Emite un evento estructurado. Nunca incluyas secretos ni datos personales completos."""
    campos.setdefault("thread_id", _thread_id.get())
    logger.log(nivel, nombre, extra={"campos": campos})
