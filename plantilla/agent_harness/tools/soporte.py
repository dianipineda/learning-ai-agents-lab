"""Tools de EJEMPLO (soporte de pedidos, simuladas). Cámbialas por las de tu dominio.

Muestran las tres clases de tool: de consulta, que puede fallar (RP-9999 simula un backend caído)
y con efectos reales (crear_reclamo: sensible + idempotente).
"""

from __future__ import annotations

import re

from .base import Tool
from .registry import ToolRegistry

_PEDIDOS = {
    "RP-1001": {"estado": "en_camino", "tiempo_restante_min": 12, "repartidor": "Carlos M."},
    "RP-1002": {"estado": "entregado", "tiempo_restante_min": 0, "repartidor": "Ana G."},
    "RP-1003": {"estado": "preparando", "tiempo_restante_min": 25, "repartidor": None},
}
_PAGOS = {
    "RP-1001": {"cobros": 2, "monto_por_cobro": 35000, "estado_pago": "cobro_duplicado"},
    "RP-1002": {"cobros": 1, "monto_por_cobro": 28000, "estado_pago": "pagado"},
    "RP-1003": {"cobros": 1, "monto_por_cobro": 41000, "estado_pago": "pagado"},
}


class SoporteBackend:
    """Sistema 'externo' simulado. Cada instancia tiene sus propios reclamos (tests aislados)."""

    def __init__(self):
        self.reclamos: dict[str, dict] = {}

    def consultar_estado_pedido(self, numero_pedido: str) -> dict:
        if numero_pedido == "RP-9999":
            raise TimeoutError("El sistema de pedidos no responde")
        return _PEDIDOS.get(numero_pedido, {"estado": "no_encontrado", "tiempo_restante_min": None, "repartidor": None})

    def consultar_pago(self, numero_pedido: str) -> dict:
        return _PAGOS.get(numero_pedido, {"cobros": 0, "estado_pago": "no_encontrado"})

    def crear_reclamo(self, numero_pedido: str, motivo: str) -> dict:
        rid = f"REC-{len(self.reclamos) + 1:04d}"
        self.reclamos[rid] = {"reclamo_id": rid, "numero_pedido": numero_pedido, "estado": "abierto", "motivo": motivo}
        return self.reclamos[rid]


def _validar_pedido(args: dict) -> str | None:
    if not re.fullmatch(r"RP-\d{4}", args.get("numero_pedido", "")):
        return f"numero_pedido inválido: {args.get('numero_pedido')!r}. El formato correcto es RP-1234."
    return None


def _validar_reclamo(args: dict) -> str | None:
    return _validar_pedido(args) or (None if args.get("motivo", "").strip() else "El motivo del reclamo no puede estar vacío.")


_PEDIDO = {"numero_pedido": {"type": "string", "description": "Ej: 'RP-1001'"}}


def crear_tools_soporte(backend: SoporteBackend | None = None) -> ToolRegistry:
    b = backend or SoporteBackend()
    return ToolRegistry([
        Tool(
            "consultar_estado_pedido", "Consulta el estado actual de un pedido dado su número.",
            {"type": "object", "properties": _PEDIDO, "required": ["numero_pedido"]},
            b.consultar_estado_pedido, validar=_validar_pedido,
        ),
        Tool(
            "consultar_pago", "Consulta los cobros registrados de un pedido (cuántos y de cuánto).",
            {"type": "object", "properties": _PEDIDO, "required": ["numero_pedido"]},
            b.consultar_pago, validar=_validar_pedido,
        ),
        Tool(
            "crear_reclamo", "Registra un reclamo formal sobre un pedido. Requiere número de pedido y motivo.",
            {"type": "object",
             "properties": {**_PEDIDO, "motivo": {"type": "string", "description": "Resumen breve del problema"}},
             "required": ["numero_pedido", "motivo"]},
            b.crear_reclamo, sensible=True, validar=_validar_reclamo,
            clave_idempotencia=lambda a: f"{a['numero_pedido']}:{a['motivo'].strip().lower()}",
        ),
    ])
