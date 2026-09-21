"""Ventana deslizante: el hilo guarda TODO, al modelo solo se le envía lo reciente.

Se corta únicamente en fronteras de TURNO (un mensaje de texto del usuario que no es un
tool_result). Cortar `historial[-n:]` a ciegas deja tool_result sin su tool_use, o un historial que no
empieza por `user`: error 400 de la API.
"""

from __future__ import annotations


def es_inicio_de_turno(mensaje: dict) -> bool:
    if mensaje["role"] != "user":
        return False
    if isinstance(mensaje["content"], str):
        return True
    return not any(b.get("type") == "tool_result" for b in mensaje["content"])


def recortar_historial(historial: list, max_mensajes: int) -> list:
    """Ventana válida y sin modificar el original. Si ni el último turno cabe, se devuelve completo."""
    inicios = [i for i, m in enumerate(historial) if es_inicio_de_turno(m)]
    if not inicios:
        return list(historial)
    for i in inicios:
        if len(historial) - i <= max_mensajes:
            return historial[i:]
    return historial[inicios[-1]:]


def validar_historial(historial: list) -> bool:
    """Reglas que la API exige: empieza en texto del usuario, alterna roles, sin tool_use huérfanos."""
    if not historial or not es_inicio_de_turno(historial[0]):
        return False
    if any(a["role"] == b["role"] for a, b in zip(historial, historial[1:])):
        return False
    for i, m in enumerate(historial):
        if m["role"] != "assistant" or isinstance(m["content"], str):
            continue
        usos = {b["id"] for b in m["content"] if b.get("type") == "tool_use"}
        if not usos:
            continue
        if i + 1 >= len(historial) or isinstance(historial[i + 1]["content"], str):
            return False
        resultados = {b["tool_use_id"] for b in historial[i + 1]["content"] if b.get("type") == "tool_result"}
        if usos != resultados:
            return False
    return True
