from __future__ import annotations

from .base import Tool


class ToolRegistry:
    """Catálogo de tools. Un agente declara los NOMBRES que usa; el registro las resuelve."""

    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.registrar(t)

    def registrar(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, nombre: str) -> Tool | None:
        return self._tools.get(nombre)

    def nombres(self) -> list[str]:
        return list(self._tools)

    def schemas(self, nombres: list[str] | tuple[str, ...]) -> list[dict]:
        faltan = [n for n in nombres if n not in self._tools]
        if faltan:
            raise KeyError(f"tools no registradas: {faltan}")
        return [self._tools[n].schema() for n in nombres]
