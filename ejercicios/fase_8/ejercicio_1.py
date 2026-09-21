"""
Fase 8 — Ejercicio 1: Aprobación humana con interrupt
=====================================================
Objetivo: que el agente PAUSE antes de una acción sensible y espere la decisión de una persona.

Hasta la fase 7 el agente ejecutaba `crear_reclamo` sin preguntar. Un agente autónomo
necesita puntos de control: las acciones con efectos reales (reclamos, reembolsos) pasan
por un humano antes de ejecutarse.

Conceptos nuevos:
  - interrupt(valor): pausa el grafo. `valor` se le muestra al humano. Cuando el grafo se
    retoma, `interrupt` DEVUELVE lo que el humano respondió.
  - Command(resume=...): así se retoma un grafo pausado, con el MISMO thread_id.
  - interrupt EXIGE un checkpointer: sin él no hay dónde guardar el state pausado.
  - Al retomar, el nodo que llamó a interrupt se EJECUTA DE NUEVO DESDE EL PRINCIPIO.
    Por eso el nodo de aprobación no debe hacer nada con efectos antes del interrupt.
  - Fallar cerrado: si falta la decisión, se trata como "no aprobado".

Flujo:
    START → clasificar → ejecutor ─┬─ (tool sensible) → aprobar → tools → ejecutor
                                   ├─ (tool segura)  ─────────→ tools → ejecutor
                                   └─ (sin tools) → END
"""

import json
import operator
from typing import Annotated, TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

MODELO = "claude-sonnet-5"

# Tools con efectos reales: requieren aprobación humana antes de ejecutarse.
SENSIBLES = {"crear_reclamo"}


# -------------------------------------------------------------------
# Funciones simuladas y tools
# -------------------------------------------------------------------
def consultar_estado_pedido(numero_pedido: str) -> dict:
    pedidos_simulados = {
        "RP-1001": {"estado": "en_camino", "tiempo_restante_min": 12, "repartidor": "Carlos M."},
        "RP-1002": {"estado": "entregado", "tiempo_restante_min": 0, "repartidor": "Ana G."},
        "RP-1003": {"estado": "preparando", "tiempo_restante_min": 25, "repartidor": None},
    }
    return pedidos_simulados.get(
        numero_pedido,
        {"estado": "no_encontrado", "tiempo_restante_min": None, "repartidor": None},
    )


RECLAMOS: dict[str, dict] = {}


def crear_reclamo(numero_pedido: str, motivo: str) -> dict:
    reclamo_id = f"REC-{len(RECLAMOS) + 1:04d}"
    RECLAMOS[reclamo_id] = {
        "reclamo_id": reclamo_id,
        "numero_pedido": numero_pedido,
        "estado": "abierto",
        "motivo": motivo,
    }
    return RECLAMOS[reclamo_id]


tools = [
    {
        "name": "consultar_estado_pedido",
        "description": "Consulta el estado actual de un pedido dado su número.",
        "input_schema": {
            "type": "object",
            "properties": {"numero_pedido": {"type": "string", "description": "Ej: 'RP-1001'"}},
            "required": ["numero_pedido"],
        },
    },
    {
        "name": "crear_reclamo",
        "description": (
            "Registra un reclamo formal sobre un pedido. Úsala cuando el usuario reporte "
            "un problema con su pedido y quiera que se registre. Requiere el número de "
            "pedido; si el usuario no lo dio, pídeselo antes de llamarla."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_pedido": {"type": "string", "description": "Ej: 'RP-1001'"},
                "motivo": {"type": "string", "description": "Resumen breve del problema"},
            },
            "required": ["numero_pedido", "motivo"],
        },
    },
]

FUNCIONES = {
    "consultar_estado_pedido": consultar_estado_pedido,
    "crear_reclamo": crear_reclamo,
}

SYSTEM_CLASIFICADOR = """
Eres un clasificador de solicitudes de soporte de pedidos. Devuelve ÚNICAMENTE JSON:
{ "tipo": "consulta_pedido" | "queja" | "saludo" | "otro", "numero_pedido": "<número o null>" }
Sin texto extra ni bloques Markdown.

Puedes recibir la clasificación ANTERIOR de la conversación. Si el mensaje nuevo es un
seguimiento (por ejemplo, solo trae un número de pedido que faltaba), conserva el `tipo`
anterior y completa `numero_pedido`. Si el mensaje cambia de tema, clasifícalo de nuevo.
"""


def construir_system_ejecutor(clasificacion: dict) -> str:
    tipo = clasificacion.get("tipo", "otro")
    numero_pedido = clasificacion.get("numero_pedido")
    return f"""
    Eres un agente de soporte de pedidos de Rappi. Eres amable, breve y resolutivo.

    ### Contexto detectado por el clasificador
    - tipo: {tipo}
    - numero_pedido: {numero_pedido} (None o null significa que no se detectó)

    ### Reglas
    1. consulta_pedido con número: usa consultar_estado_pedido y responde con lo que devuelva.
    2. queja con número: primero consultar_estado_pedido, luego crear_reclamo.
       Empieza con una disculpa sincera y entrega el ID del reclamo.
    3. Si falta el número de pedido, pídeselo al usuario antes de usar herramientas.
    4. Nunca inventes datos, procesos, políticas, plazos ni acciones. Solo puedes
       consultar estados y registrar reclamos. No prometas nada que las herramientas
       no confirmen.
    5. saludo: responde con calidez, sin herramientas. otro: explica que solo ayudas con pedidos.
    6. Si un supervisor humano RECHAZA una acción (tool_result con error), no la reintentes:
       explícale al usuario que no se pudo registrar y que un agente humano lo contactará.
    """


def bloques_a_dict(content) -> list[dict]:
    """Convierte los bloques del SDK en dicts simples (serializables por el checkpointer)."""
    salida = []
    for b in content:
        if b.type == "text":
            salida.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            salida.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return salida


# -------------------------------------------------------------------
# BLANK 1 — El State guarda la decisión humana
# -------------------------------------------------------------------
# El nodo `aprobar` va a escribir la decisión del humano y `tools_node` la va a leer.
# Como el nodo de aprobación y el de tools son nodos distintos, la decisión viaja por el state.
#
# Agrega al State un campo `aprobado` de tipo bool. Sin reducer: es "el estado actual de
# algo", se reemplaza (recuerda la regla de la fase 7).
class Estado(TypedDict):
    mensaje: str
    clasificacion: dict
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str
    ___BLANK_1___


def clasificar(estado: Estado) -> dict:
    previa = estado.get("clasificacion")
    contenido = f"Clasificación anterior: {previa}\nMensaje nuevo: {estado['mensaje']}"
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=SYSTEM_CLASIFICADOR,
        messages=[{"role": "user", "content": contenido}],
    )
    texto = next(b.text for b in respuesta.content if b.type == "text").strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    clasificacion = json.loads(texto)
    print(f"  [clasificador] → {clasificacion}")
    return {"clasificacion": clasificacion}


def ejecutor(estado: Estado) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=1024,
        system=construir_system_ejecutor(estado["clasificacion"]),
        tools=tools,
        messages=estado["historial"],
    )
    texto = next((b.text for b in respuesta.content if b.type == "text"), "")
    print(f"  [ejecutor] stop_reason={respuesta.stop_reason}")
    return {
        "historial": [{"role": "assistant", "content": bloques_a_dict(respuesta.content)}],
        "stop_reason": respuesta.stop_reason,
        "respuesta": texto,
    }


# -------------------------------------------------------------------
# BLANK 2 — Pausar el grafo y esperar al humano
# -------------------------------------------------------------------
# Este nodo junta las acciones sensibles que Claude quiere ejecutar y le pregunta a una
# persona. Ya está armada la lista `acciones`. Falta la línea que PAUSA el grafo:
#
#     aprobado = <la función de LangGraph que pausa>(<lo que se le muestra al humano>)
#
# `interrupt` devuelve lo que el humano responda al retomar (aquí: un bool).
# Muéstrale la lista `acciones`.
#
# Pregunta para razonar: al retomar, este nodo corre otra vez desde la primera línea.
# ¿Qué pasaría si antes del interrupt llamáramos a `crear_reclamo`?
def aprobar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    acciones = [
        {"tool": b["name"], "argumentos": b["input"]}
        for b in ultimo["content"]
        if b["type"] == "tool_use" and b["name"] in SENSIBLES
    ]
    aprobado = ___BLANK_2___
    return {"aprobado": aprobado}


def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    # Fallar cerrado: si por algún motivo no hay decisión, NO se ejecuta lo sensible.
    aprobado = estado.get("aprobado", False)
    resultados = []
    for bloque in ultimo["content"]:
        if bloque["type"] != "tool_use":
            continue
        if bloque["name"] in SENSIBLES and not aprobado:
            print(f"  [tools] {bloque['name']} RECHAZADA por el humano")
            resultados.append({
                "type": "tool_result",
                "tool_use_id": bloque["id"],
                "content": "Acción rechazada por un supervisor humano. No se ejecutó.",
                "is_error": True,
            })
            continue
        print(f"  [tools] {bloque['name']}({bloque['input']})")
        resultado = FUNCIONES[bloque["name"]](**bloque["input"])
        resultados.append({
            "type": "tool_result",
            "tool_use_id": bloque["id"],
            "content": json.dumps(resultado),
        })
    return {"historial": [{"role": "user", "content": resultados}]}


# -------------------------------------------------------------------
# BLANK 3 — Rutear según la sensibilidad de las tools
# -------------------------------------------------------------------
# Ahora `decidir` tiene 3 salidas:
#   - stop_reason != "tool_use"                        → END
#   - hay algún tool_use cuyo name esté en SENSIBLES   → "aprobar"
#   - si no                                            → "tools"
#
# Pista: el último mensaje del historial es el del assistant; sus bloques son dicts
# (b["type"], b["name"]). Puedes usar any(...) con una condición sobre cada bloque.
def decidir(estado: Estado) -> str:
    if estado["stop_reason"] != "tool_use":
        return END
    ultimo = estado["historial"][-1]
    hay_sensible = ___BLANK_3___
    return "aprobar" if hay_sensible else "tools"


# -------------------------------------------------------------------
# BLANK 4 — Cablear el nodo de aprobación
# -------------------------------------------------------------------
# 4a: registra el nodo "aprobar" (función `aprobar`).
# 4b: el mapa de add_conditional_edges necesita ahora 3 salidas: aprobar, tools y END.
# 4c: "aprobar" siempre sigue a "tools" (una arista fija).
#
# Y recuerda: interrupt necesita checkpointer (ya lo tienes en compile).
builder = StateGraph(Estado)
builder.add_node("clasificar", clasificar)
builder.add_node("ejecutor", ejecutor)
___BLANK_4a___
builder.add_node("tools", tools_node)

builder.add_edge(START, "clasificar")
builder.add_edge("clasificar", "ejecutor")
builder.add_conditional_edges("ejecutor", decidir, ___BLANK_4b___)
___BLANK_4c___
builder.add_edge("tools", "ejecutor")

memoria = MemorySaver()
grafo = builder.compile(checkpointer=memoria)


# -------------------------------------------------------------------
# BLANK 5 — Detectar la pausa y retomar
# -------------------------------------------------------------------
# Cuando el grafo se pausa, `invoke` NO lanza error: devuelve el state con una clave
# especial "__interrupt__" (una lista de objetos Interrupt; el valor que pasaste a
# interrupt() está en `.value`).
#
# 5a: condición para saber si el grafo quedó pausado (la clave está en el resultado).
# 5b: retomar el grafo con el MISMO config, pasando a invoke un objeto Command que lleve
#     la decisión (bool) como `resume`. Es un while porque tras aprobar podría haber otra pausa.
print("Agente de soporte con aprobación humana — 'nuevo' otra conversación, 'salir' termina\n")

contador_hilos = 1

while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir":
        print("¡Hasta luego!")
        break
    if user_input.lower() == "nuevo":
        contador_hilos += 1
        print(f"\n(nueva conversación: hilo {contador_hilos})\n")
        continue

    config = {"configurable": {"thread_id": f"conversacion-{contador_hilos}"}, "recursion_limit": 10}

    print()
    try:
        resultado = grafo.invoke(
            {"mensaje": user_input, "historial": [{"role": "user", "content": user_input}]},
            config,
        )
        while ___BLANK_5a___:
            acciones = resultado["__interrupt__"][0].value
            print("\n⏸  Acción pendiente de aprobación:")
            for a in acciones:
                print(f"   - {a['tool']}({a['argumentos']})")
            decision = input("¿Aprobar? (s/n): ").strip().lower() == "s"
            print()
            resultado = ___BLANK_5b___
        print(f"\nAgente: {resultado['respuesta']}\n")
    except GraphRecursionError:
        print("\nAgente: Lo siento, no pude completar tu solicitud. Un agente humano te contactará.\n")
