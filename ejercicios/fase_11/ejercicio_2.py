"""
Fase 11 — Ejercicio 2: streaming y observabilidad con LangGraph
================================================================
Problema: hoy el orquestador trabaja "en silencio": llamas a `invoke` y esperas al final. Un
agente autónomo que tarda 20 segundos sin mostrar nada parece colgado, y cuando falla no sabes
en qué nodo. `stream` te deja ver cada paso MIENTRAS ocurre.

Modos de `grafo.stream(entrada, config, stream_mode=...)`:
  "updates" → un chunk por nodo terminado, con SOLO lo que ese nodo devolvió. Es el modo para
              pintar progreso ("entró pedidos", "llamó a la tool"). Ojo: NO es el estado
              acumulado; si `traza` usa un reducer, aquí ves solo lo que agregó ese nodo.
  "values"  → el estado COMPLETO tras cada paso. Es el modo para auditar; el último chunk es el
              estado final.
  "custom"  → eventos que TÚ emites desde dentro de un nodo con `get_stream_writer()`. Es la vía
              para reportar progreso fino (p. ej. "consultando pedido…") con el SDK de Anthropic.
  ("messages" es para modelos de LangChain; con el SDK crudo no emite nada, por eso aquí no se usa.)

Se pueden pedir varios a la vez: `stream_mode=["updates", "custom"]` → cada chunk llega como
tupla `(modo, contenido)`.

Con `interrupt` (fase 8) el stream se PAUSA: aparece un chunk especial con la clave
"__interrupt__" (su valor es una tupla de `Interrupt`; la pregunta está en `.value`) y el stream
termina. Para seguir se hace streaming de `Command(resume=...)` con el MISMO thread_id.

El grafo de este ejercicio es de juguete y NO usa la API (así se prueba sin gastar):
    START → clasificar ─┬─ pedidos ───────────────→ END
                        └─ aprobar (interrupt) → reclamos → END

Ejecutar (desde la raíz del repo):
    python ejercicios/fase_11/ejercicio_2.py
"""

import operator
import sys
import uuid
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class Estado(TypedDict):
    mensaje: str
    agente: str
    respuesta: str
    aprobado: bool
    traza: Annotated[list, operator.add]


def clasificar(estado: Estado) -> dict:
    agente = "reclamos" if "reclamo" in estado["mensaje"].lower() else "pedidos"
    return {"agente": agente, "traza": ["clasificar"]}


def pedidos(estado: Estado) -> dict:
    escritor = ___BLANK_1___  # canal para emitir eventos propios ("custom")
    escritor({"progreso": "consultando el pedido…"})
    return {"respuesta": "Tu pedido va en camino", "traza": ["pedidos"]}


def aprobar(estado: Estado) -> dict:
    decision = interrupt({"pregunta": "¿Registrar el reclamo?"})
    return {"aprobado": bool(decision), "traza": ["aprobar"]}


def reclamos(estado: Estado) -> dict:
    respuesta = "Reclamo registrado" if estado["aprobado"] else "No se registró el reclamo"
    return {"respuesta": respuesta, "traza": ["reclamos"]}


def construir():
    g = StateGraph(Estado)
    for nombre, nodo in [("clasificar", clasificar), ("pedidos", pedidos), ("aprobar", aprobar), ("reclamos", reclamos)]:
        g.add_node(nombre, nodo)
    g.add_edge(START, "clasificar")
    g.add_conditional_edges("clasificar", lambda e: e["agente"], {"pedidos": "pedidos", "reclamos": "aprobar"})
    g.add_edge("pedidos", END)
    g.add_edge("aprobar", "reclamos")
    g.add_edge("reclamos", END)
    return g.compile(checkpointer=MemorySaver())


def correr(grafo, entrada, config, on_evento):
    """Consume el stream, avisa cada evento a `on_evento(nombre, datos)` y devuelve la pregunta
    pendiente (payload del interrupt) o None si el grafo terminó."""
    pendiente = None
    for modo, chunk in grafo.stream(entrada, config, stream_mode=___BLANK_2___):
        if modo == "custom":
            on_evento("progreso", chunk)
            continue
        for nodo, cambios in chunk.items():
            if nodo == ___BLANK_3___:
                pendiente = ___BLANK_4___
            else:
                on_evento(nodo, cambios)
    return pendiente


def conversar(grafo, mensaje, decision, on_evento):
    """Un turno completo: corre, y si el grafo pide aprobación, reanuda con `decision`."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    pendiente = correr(grafo, {"mensaje": mensaje}, config, on_evento)
    preguntas = []
    if pendiente is not None:
        preguntas.append(pendiente["pregunta"])
        correr(grafo, ___BLANK_5___, config, on_evento)
    return preguntas, grafo.get_state(config).values


def estado_por_stream(grafo, mensaje):
    """Auditoría: el último chunk de stream_mode='values' ES el estado final."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    ultimo = None
    for chunk in grafo.stream({"mensaje": mensaje}, config, stream_mode=___BLANK_6___):
        ultimo = chunk
    return ultimo, grafo.get_state(config).values


def main() -> int:
    fallos = 0

    def chequear(nombre, condicion):
        nonlocal fallos
        print(f"  {'✓' if condicion else '✗'} {nombre}")
        fallos += 0 if condicion else 1

    grafo = construir()

    print("Consulta de pedido (sin interrupt):")
    eventos = []
    preguntas, final = conversar(grafo, "¿Cómo va mi pedido?", True, lambda n, d: eventos.append((n, d)))
    chequear("orden de eventos: clasificar → progreso → pedidos", [n for n, _ in eventos] == ["clasificar", "progreso", "pedidos"])
    chequear("el evento 'progreso' trae lo que emitió el nodo", eventos[1][1] == {"progreso": "consultando el pedido…"})
    chequear("no hubo pregunta al humano", preguntas == [])
    chequear("un chunk 'updates' trae SOLO lo que devolvió el nodo", eventos[0][1] == {"agente": "pedidos", "traza": ["clasificar"]})

    print("Reclamo aprobado (interrupt + reanudación):")
    eventos = []
    preguntas, final = conversar(grafo, "Quiero un reclamo", True, lambda n, d: eventos.append((n, d)))
    chequear("el stream mostró la pregunta antes de terminar", preguntas == ["¿Registrar el reclamo?"])
    chequear("orden de eventos: clasificar → aprobar → reclamos", [n for n, _ in eventos] == ["clasificar", "aprobar", "reclamos"])
    chequear("respuesta final 'Reclamo registrado'", final["respuesta"] == "Reclamo registrado")

    print("Reclamo rechazado:")
    preguntas, final = conversar(grafo, "Quiero un reclamo", False, lambda n, d: None)
    chequear("respuesta final 'No se registró el reclamo'", final["respuesta"] == "No se registró el reclamo")

    print("Modo 'values' (auditoría):")
    ultimo, guardado = estado_por_stream(grafo, "¿Cómo va mi pedido?")
    chequear("el último chunk es el estado final guardado", ultimo == guardado)
    chequear("en 'values' la traza SÍ está acumulada", ultimo["traza"] == ___BLANK_7___)

    print(f"\nResultado: {'OK' if fallos == 0 else f'{fallos} chequeos fallaron'}")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
