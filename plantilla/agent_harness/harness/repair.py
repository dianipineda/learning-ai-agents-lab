"""Cierre de historiales: cada tool_use necesita su tool_result y el historial debe terminar en assistant."""

from __future__ import annotations


def resultados_no_ejecutados(mensaje_assistant: dict, motivo: str) -> list[dict]:
    """Un tool_result de error por cada tool_use del mensaje."""
    return [
        {"type": "tool_result", "tool_use_id": b["id"], "content": motivo, "is_error": True}
        for b in mensaje_assistant["content"]
        if b["type"] == "tool_use"
    ]


def cerrar_historial(historial: list, texto_cierre: str, motivo: str) -> list:
    """Mensajes a AGREGAR para dejar el historial bien formado y terminado. [] si ya lo está.

    Sirve tanto para el corte por presupuesto como para reparar un hilo cortado por
    GraphRecursionError (que puede dejar un assistant con tool_use sin respuesta).
    """
    if not historial:
        return []
    cierre = {"role": "assistant", "content": [{"type": "text", "text": texto_cierre}]}
    ultimo = historial[-1]
    if ultimo["role"] == "assistant":
        resultados = resultados_no_ejecutados(ultimo, motivo)
        return [{"role": "user", "content": resultados}, cierre] if resultados else []
    return [cierre]
