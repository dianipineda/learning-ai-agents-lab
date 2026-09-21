"""
Fase 11 — Ejercicio 1: ventana deslizante sobre el historial
============================================================
Problema: con memoria por hilo (fase 10) cada mensaje nuevo reenvía TODA la conversación al
modelo. El costo y la latencia crecen en cada turno, y el único freno que tenía el orquestador
era un corte duro de presupuesto (el agente se rinde).

Solución: guardar el historial COMPLETO en el estado (auditoría), pero enviar al modelo solo
una ventana reciente. Lo difícil no es cortar: es cortar BIEN.

  Cortar "los últimos N mensajes" a ciegas rompe la API:
    - si la ventana empieza con un `tool_result`, su `tool_use` quedó fuera → error 400;
    - si empieza con un mensaje del asistente, el historial no empieza por `user` → error 400;
    - si parte un turno a la mitad, el modelo pierde el contexto de lo que estaba haciendo.

  Regla segura: cortar SOLO en fronteras de TURNO. Un turno empieza con un mensaje de texto del
  usuario (no un tool_result) y llega hasta antes del siguiente mensaje de texto del usuario.
  Se elige el turno más antiguo que aún cabe en `max_mensajes`. Si ni el último turno cabe,
  se devuelve ese turno completo (mejor pasarse de N que romper un turno).

El ejercicio no usa la API: el historial son diccionarios con el formato de Anthropic.

Ejecutar (desde la raíz del repo):
    python ejercicios/fase_11/ejercicio_1.py
"""

import sys


def es_inicio_de_turno(mensaje: dict) -> bool:
    """True si el mensaje abre un turno: es del usuario y NO es un bloque de tool_result."""
    if mensaje["role"] != "user":
        return False
    if isinstance(mensaje["content"], str):
        return True
    return not any(bloque.get("type") == ___BLANK_1___ for bloque in mensaje["content"])


def recortar_historial(historial: list, max_mensajes: int) -> list:
    """Devuelve una ventana válida del historial SIN modificar el original."""
    inicios = [i for i, m in enumerate(historial) if es_inicio_de_turno(m)]
    if not inicios:
        return list(historial)
    for i in inicios:  # del turno más antiguo al más reciente
        if ___BLANK_2___:
            return historial[i:]
    return historial[___BLANK_3___:]  # ni el último turno cabe: se devuelve completo


def validar_historial(historial: list) -> bool:
    """Reglas que la API exige: empieza en texto del usuario, alterna roles y no deja tool_use huérfanos."""
    if not historial or not es_inicio_de_turno(historial[0]):
        return False
    for anterior, actual in zip(historial, historial[1:]):
        if anterior["role"] == actual["role"]:
            return False
    for i, m in enumerate(historial):
        if m["role"] != "assistant" or isinstance(m["content"], str):
            continue
        ids_uso = {b["id"] for b in m["content"] if b.get("type") == "tool_use"}
        if not ids_uso:
            continue
        if i + 1 >= len(historial) or isinstance(historial[i + 1]["content"], str):
            return False
        ids_resultado = {
            b["tool_use_id"] for b in historial[i + 1]["content"] if b.get("type") == "tool_result"
        }
        if ___BLANK_4___:
            return False
    return True


# --- historial de prueba: 4 turnos, con bucles de tools (uno con 2 tools en paralelo) ---
def texto(rol, contenido):
    return {"role": rol, "content": contenido}


def uso(*ids):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": i, "name": "t", "input": {}} for i in ids]}


def resultado(*ids):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": "ok"} for i in ids]}


HISTORIAL = [
    texto("user", "hola"), texto("assistant", "¡hola!"),                                    # turno 1 (2 msgs)
    texto("user", "¿mi pedido?"), uso("a1"), resultado("a1"), uso("a2"), resultado("a2"),
    texto("assistant", "va en camino"),                                                     # turno 2 (6 msgs)
    texto("user", "gracias"), texto("assistant", "de nada"),                                # turno 3 (2 msgs)
    texto("user", "¿y el pago?"), uso("b1", "b2"), resultado("b1", "b2"),
    texto("assistant", "pagado"),                                                           # turno 4 (4 msgs)
]


def turno_simulado(historial: list, max_mensajes: int) -> list:
    """Lo que haría el agente en un turno: agrega el mensaje y arma lo que se ENVÍA al modelo."""
    historial.append(texto("user", "otra pregunta"))
    enviados = ___BLANK_5___
    historial.append(texto("assistant", "respuesta"))
    return enviados


def main() -> int:
    fallos = 0

    def chequear(nombre, condicion):
        nonlocal fallos
        print(f"  {'✓' if condicion else '✗'} {nombre}")
        fallos += 0 if condicion else 1

    print("Historial de prueba válido:")
    chequear(f"el historial de {len(HISTORIAL)} mensajes es válido", validar_historial(HISTORIAL))

    print("Tamaños exactos de la ventana:")
    for max_mensajes, esperado in [(100, 14), (12, 12), (6, 6), (5, 4), (3, 4), (1, 4)]:
        ventana = recortar_historial(HISTORIAL, max_mensajes)
        chequear(f"max={max_mensajes:>3} → {esperado} mensajes (salió {len(ventana)})", len(ventana) == esperado)

    print("Propiedades para TODO tamaño de ventana:")
    copia = [dict(m) for m in HISTORIAL]
    chequear(
        "toda ventana es válida para la API",
        all(validar_historial(recortar_historial(HISTORIAL, n)) for n in range(1, len(HISTORIAL) + 2)),
    )
    chequear(
        "toda ventana es un sufijo del historial (no se reordena ni se inventa nada)",
        all(HISTORIAL[len(HISTORIAL) - len(v):] == v for v in (recortar_historial(HISTORIAL, n) for n in range(1, 16))),
    )
    chequear("el historial original no se modifica", HISTORIAL == copia)
    chequear("con historial corto se devuelve todo", recortar_historial(HISTORIAL[:2], 10) == HISTORIAL[:2])

    print("Por qué NO basta con cortar a ciegas:")
    chequear(
        "el corte ingenuo historial[-n:] genera al menos una ventana inválida",
        ___BLANK_6___,
    )

    print("Simulación de un turno (el estado guarda TODO, el modelo recibe la ventana):")
    historial = list(HISTORIAL)
    enviados = turno_simulado(historial, 6)
    chequear("lo enviado es válido y termina en la pregunta nueva", validar_historial(enviados) and enviados[-1]["content"] == "otra pregunta")
    chequear("el estado conserva los 16 mensajes", len(historial) == len(HISTORIAL) + 2)

    print(f"\nResultado: {'OK' if fallos == 0 else f'{fallos} chequeos fallaron'}")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
