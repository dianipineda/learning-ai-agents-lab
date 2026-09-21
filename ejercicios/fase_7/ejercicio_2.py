"""
Fase 7 — Ejercicio 2: El loop de tools como grafo
==================================================
Objetivo: reescribir el `for _ in range(MAX_ITERACIONES)` de la Fase 6 como un grafo
con un CICLO y una arista CONDICIONAL.

  START → [clasificar] → [ejecutor] ──(¿pidió tool?)──► [tools] ─┐
                              ▲                  │               │
                              │                  └─ no ─► END    │
                              └──────────────────────────────────┘

Mapa Fase 6 → Fase 7:
  - `if stop_reason != "tool_use": return ...`  →  función de ruteo + arista condicional
  - el bloque que ejecuta las tools              →  nodo `tools`
  - `for _ in range(MAX_ITERACIONES)`            →  `recursion_limit` en invoke()
  - la variable `historial`                      →  un campo del State

Concepto nuevo — ARISTA CONDICIONAL:
  builder.add_conditional_edges(nodo_origen, funcion_de_ruteo, mapa)
  La función de ruteo recibe el state y devuelve el NOMBRE del siguiente nodo (o END).
  No modifica el state: solo decide el camino.

Ojo: si un nodo devuelve un campo, ese valor REEMPLAZA al anterior (no se acumula).
Para "agregar" al historial hay que devolver la lista anterior + lo nuevo.
"""

import json
from typing import TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

MODELO = "claude-sonnet-5"


# -------------------------------------------------------------------
# Funciones simuladas y tools (igual que la Fase 6)
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


def crear_reclamo(numero_pedido: str, motivo: str) -> dict:
    return {"reclamo_id": f"REC-{numero_pedido[-4:]}", "estado": "abierto", "motivo": motivo}


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
    """


# -------------------------------------------------------------------
# BLANK 1 — El State
# -------------------------------------------------------------------
# Ahora el state carga más cosas. Declara cinco campos:
#   - mensaje: str           (lo que escribió el usuario)
#   - clasificacion: dict    (lo llena `clasificar`)
#   - historial: list        (la lista `messages` que se le pasa a la API)
#   - stop_reason: str       (por qué paró Claude; lo lee la función de ruteo)
#   - respuesta: str         (el texto final para el usuario)
#
# Pista: son cinco líneas `nombre: tipo`, igual que en el ejercicio 1.
class Estado(TypedDict):
    ___BLANK_1___


def clasificar(estado: Estado) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=SYSTEM_CLASIFICADOR,
        messages=[{"role": "user", "content": estado["mensaje"]}],
    )
    texto = next(b.text for b in respuesta.content if b.type == "text").strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    clasificacion = json.loads(texto)
    print(f"  [clasificador] → {clasificacion}")
    return {"clasificacion": clasificacion}


# -------------------------------------------------------------------
# BLANK 2 — El nodo `ejecutor`
# -------------------------------------------------------------------
# Hace UNA llamada a Claude con el historial actual. No hay `for` ni `while` aquí:
# el ciclo lo va a dar el grafo, no este código.
#
# Debe devolver un dict PARCIAL con tres campos:
#   - "historial":   la lista anterior MÁS el mensaje assistant nuevo
#                    ({"role": "assistant", "content": respuesta.content})
#   - "stop_reason": respuesta.stop_reason
#   - "respuesta":   `texto` (el texto del turno; vacío si solo pidió tools)
#
# Pregunta para razonar: si devolvieras "historial" con SOLO el mensaje nuevo
# (sin la lista anterior), ¿qué le pasaría al historial en el state?
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
    return ___BLANK_2___


# -------------------------------------------------------------------
# BLANK 3 — El nodo `tools`
# -------------------------------------------------------------------
# Ejecuta TODAS las tools pedidas en el último mensaje (el assistant que guardó
# `ejecutor`) y agrega UN mensaje user con todos los tool_result.
#
# 3a: ejecuta la tool con el despachador (Fase 6, blank 5).
# 3b: devuelve el historial anterior + el mensaje user con `resultados`.
def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    resultados = []
    for bloque in ultimo["content"]:
        if bloque.type == "tool_use":
            print(f"  [tools] {bloque.name}({bloque.input})")
            resultado = ___BLANK_3a___
            resultados.append({
                "type": "tool_result",
                "tool_use_id": bloque.id,
                "content": json.dumps(resultado),
            })
    return ___BLANK_3b___


# -------------------------------------------------------------------
# BLANK 4 — La función de ruteo
# -------------------------------------------------------------------
# Reemplaza el `if respuesta.stop_reason != "tool_use"` de la Fase 6.
# Recibe el state y devuelve el nombre del SIGUIENTE nodo:
#   - "tools" si Claude pidió una tool (stop_reason == "tool_use")
#   - END     si terminó
#
# Pista: una sola línea con expresión condicional, o un if/else.
def decidir(estado: Estado) -> str:
    ___BLANK_4___


# -------------------------------------------------------------------
# BLANK 5 — Cablear el grafo con el ciclo
# -------------------------------------------------------------------
builder = StateGraph(Estado)
builder.add_node("clasificar", clasificar)
builder.add_node("ejecutor", ejecutor)
builder.add_node("tools", tools_node)

builder.add_edge(START, "clasificar")
builder.add_edge("clasificar", "ejecutor")

# 5a: arista condicional desde "ejecutor":
#     builder.add_conditional_edges("ejecutor", decidir, {"valor_que_devuelve_decidir": "nodo_destino", ...})
#     El mapa tiene dos entradas: una para "tools" y otra para END.
___BLANK_5a___

# 5b: cierra el CICLO: después de "tools" se vuelve a "ejecutor".
___BLANK_5b___

grafo = builder.compile()


# -------------------------------------------------------------------
# BLANK 6 — Ejecutar con límite de pasos
# -------------------------------------------------------------------
# El guardrail `MAX_ITERACIONES` ahora es `recursion_limit`: el máximo de pasos
# (ejecuciones de nodos) que LangGraph permite antes de lanzar GraphRecursionError.
#
# Se pasa en el segundo argumento de invoke:  grafo.invoke(estado_inicial, config={...})
# Usa recursion_limit = 10.
#
# El state inicial lleva `mensaje` y el `historial` con el primer mensaje user.
print("Agente de soporte como grafo — escribe 'salir' para terminar\n")

while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir":
        print("¡Hasta luego!")
        break

    print()
    try:
        estado_final = ___BLANK_6___
        print(f"\nAgente: {estado_final['respuesta']}\n")
    except GraphRecursionError:
        print("\nAgente: Lo siento, no pude completar tu solicitud. Un agente humano te contactará.\n")
