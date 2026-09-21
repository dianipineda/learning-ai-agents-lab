"""Contrato de una tool. Toda tool declara QUÉ hace (schema) y CÓMO debe tratarse (política)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

_TIPOS = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    funcion: Callable[..., Any]
    sensible: bool = False  # efectos reales → exige aprobación humana antes de ejecutarse
    validar: Callable[[dict], str | None] | None = None  # regla de negocio extra sobre los argumentos
    clave_idempotencia: Callable[[dict], str] | None = None  # misma clave = misma operación (no se repite)

    def schema(self) -> dict:
        """Lo que se envía a la API."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def validar_args(self, args: dict) -> str | None:
        """Mensaje de error (para el modelo) si los argumentos no sirven; None si están bien."""
        props = self.input_schema.get("properties", {})
        for requerido in self.input_schema.get("required", []):
            if requerido not in args:
                return f"Falta el argumento obligatorio '{requerido}'."
        for nombre, valor in args.items():
            esquema = props.get(nombre)
            if esquema is None:
                return f"Argumento desconocido '{nombre}'."
            tipo = _TIPOS.get(esquema.get("type"))
            if tipo and (not isinstance(valor, tipo) or (esquema["type"] != "boolean" and isinstance(valor, bool))):
                return f"El argumento '{nombre}' debe ser de tipo {esquema['type']}."
            if "enum" in esquema and valor not in esquema["enum"]:
                return f"'{nombre}' debe ser uno de {esquema['enum']}."
        return self.validar(args) if self.validar else None
