"""Memoria por hilo. ':memory:' es volátil (dev/tests); una ruta usa SQLite y sobrevive reinicios.
Para escalar horizontalmente cambia esto por un checkpointer de Postgres/Redis: el resto no se entera."""

from __future__ import annotations

import sqlite3


def crear_checkpointer(ruta: str = ":memory:"):
    if ruta == ":memory:":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver(sqlite3.connect(ruta, check_same_thread=False))
