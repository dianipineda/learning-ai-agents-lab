"""
Fase 7 — Ejercicio 3: Memoria entre turnos con un checkpointer
==============================================================
Objetivo: que el agente RECUERDE la conversación sin que tú pases el historial a mano.

En el ejercicio 2 cada `invoke` empezaba de cero: tú reconstruías `historial` en el
state inicial y el clasificador etiquetaba mal los seguimientos ("RP-1002" solo →
`consulta_pedido` aunque venías de una queja).

Conceptos nuevos:
  - CHECKPOINTER: guarda el state después de cada paso. Se le pasa a compile().
  - THREAD: una conversación. Se identifica con un `thread_id` en el config de invoke().
    Mismo thread_id → LangGraph carga el state guardado. Otro thread_id → arranca limpio.
  - REDUCER: regla para COMBINAR el valor nuevo de un campo con el anterior.
    Sin reducer, un campo se REEMPLAZA (ejercicio 2). Con `Annotated[list, operator.add]`
    se CONCATENA: los nodos devuelven solo lo nuevo y LangGraph lo agrega.

Nota: los mensajes assistant se guardan como dicts simples (no como objetos del SDK)
porque el checkpointer necesita serializar el state. Ver `bloques_a_dict`.
"""

import json
import operator
from typing import Annotated, TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

MODELO = "claude-sonnet-5"


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


# Store de reclamos: ahora los IDs son únicos aunque el pedido se repita.
# (Antes: `REC-{últimos 4 del pedido}` → dos reclamos de RP-1001 colisionaban en REC-1001.)
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
# BLANK 1 — El State con REDUCER
# -------------------------------------------------------------------
# Igual que el ejercicio 2, pero `historial` ahora se ACUMULA en vez de reemplazarse.
# Un reducer se declara con Annotated:
#
#     campo: Annotated[tipo, funcion_reductora]
#
# `operator.add` sobre listas las concatena: [a] + [b] → [a, b].
# Declara `historial` con ese reducer. Los demás campos quedan como están.
#
# Pregunta para razonar: ¿por qué NO conviene ponerle reducer a `respuesta` ni a
# `stop_reason`?
class Estado(TypedDict):
    mensaje: str
    clasificacion: dict
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str


# -------------------------------------------------------------------
# BLANK 2 — El clasificador con memoria
# -------------------------------------------------------------------
# Como el state se guarda entre turnos, `estado.get("clasificacion")` trae la
# clasificación del turno anterior (o None en el primer turno).
#
# Construye `contenido`: un string que incluya la clasificación anterior y el mensaje
# nuevo, para que el clasificador pueda detectar seguimientos. Por ejemplo:
#     "Clasificación anterior: {...}\nMensaje nuevo: ..."
# (usa un f-string con `previa` y `estado["mensaje"]`).
def clasificar(estado: Estado) -> dict:
    previa = estado.get("clasificacion")
    contenido =  f"Clasificación anterior: {previa}\nMensaje nuevo: {estado['mensaje']}"
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


# -------------------------------------------------------------------
# BLANK 3 — Nodos que devuelven SOLO lo nuevo
# -------------------------------------------------------------------
# Con el reducer, ya no hace falta `estado["historial"] + [...]`: LangGraph concatena.
# Cada nodo devuelve una lista con SOLO el mensaje que agrega.
#
# 3a (ejecutor): historial = lista con el mensaje assistant nuevo, usando
#                content=bloques_a_dict(respuesta.content). Más stop_reason y respuesta.
# 3b (tools_node): historial = lista con el mensaje user que lleva `resultados`.
#
# Pregunta para razonar: si dejaras `estado["historial"] + [...]` CON el reducer,
# ¿qué le pasaría al historial?
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


def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    resultados = []
    for bloque in ultimo["content"]:
        if bloque["type"] == "tool_use":
            print(f"  [tools] {bloque['name']}({bloque['input']})")
            resultado = FUNCIONES[bloque["name"]](**bloque["input"])
            resultados.append({
                "type": "tool_result",
                "tool_use_id": bloque["id"],
                "content": json.dumps(resultado),
            })
    return {
        "historial": [{"role": "user", "content": resultados}],
    }


def decidir(estado: Estado) -> str:
    return "tools" if estado["stop_reason"] == "tool_use" else END


# -------------------------------------------------------------------
# BLANK 4 — Compilar con checkpointer
# -------------------------------------------------------------------
builder = StateGraph(Estado)
builder.add_node("clasificar", clasificar)
builder.add_node("ejecutor", ejecutor)
builder.add_node("tools", tools_node)

builder.add_edge(START, "clasificar")
builder.add_edge("clasificar", "ejecutor")
builder.add_conditional_edges("ejecutor", decidir, {"tools": "tools", END: END})
builder.add_edge("tools", "ejecutor")

# Crea el checkpointer en memoria y pásalo a compile():
#     memoria = MemorySaver()
#     grafo = builder.compile(checkpointer=memoria)
# (En producción se usaría uno persistente, p. ej. SQLite o Postgres; la API es la misma.)
memoria = MemorySaver()
grafo = builder.compile(checkpointer=memoria)

# -------------------------------------------------------------------
# BLANK 5 — Invocar con thread_id
# -------------------------------------------------------------------
# El thread_id va en el config, dentro de "configurable":
#     config = {"configurable": {"thread_id": "conversacion-1"}, "recursion_limit": 10}
#
# Ahora el input de invoke lleva SOLO lo nuevo de este turno: el mensaje y el mensaje
# user. LangGraph carga el historial guardado y le agrega este (por el reducer).
#
# Escribe `config` (usa `thread_id` para el id) y la llamada a invoke.
print("Agente de soporte con memoria — 'nuevo' inicia otra conversación, 'salir' termina\n")

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

    thread_id = f"conversacion-{contador_hilos}"

    print()
    try:
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 10}
        estado_final = grafo.invoke(
            {"mensaje": user_input, "historial": [{"role": "user", "content": user_input}]},
            config,
        )
        print(f"\nAgente: {estado_final['respuesta']}\n")
    except GraphRecursionError:
        print("\nAgente: Lo siento, no pude completar tu solicitud. Un agente humano te contactará.\n")
