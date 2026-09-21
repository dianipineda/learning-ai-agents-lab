"""
Fase 8 — Ejercicio 3: Robustez (reintentos, timeouts y errores que no rompen al agente)
=======================================================================================
Objetivo: que el agente siga siendo útil cuando algo falla: la API se cae, una tool lanza
una excepción, o la respuesta del modelo viene mal formada.

Al agente del ejercicio 2 (aprobación humana + guardrails, ya resueltos aquí) le sumamos
tres capas de defensa, de la más externa a la más interna:

  1. CLIENTE: el SDK reintenta solo los errores transitorios (red, 429, 5xx) con espera
     creciente. Tú decides cuántos reintentos (`max_retries`) y cuánto esperar (`timeout`).
  2. NODO: si aun así la API falla, el nodo captura `anthropic.APIError` y responde con
     un mensaje amable en vez de tumbar el programa. IMPORTANTE: el historial debe seguir
     alternando user/assistant. Si el nodo solo devolviera `respuesta` sin agregar un
     mensaje assistant, el siguiente turno mandaría dos `user` seguidos y daría error 400
     (el mismo problema del edge case pendiente de la fase 7).
  3. TOOL: si una función lanza una excepción, se devuelve como `tool_result` con
     `is_error: True`. Claude lo lee y le explica al usuario, en vez de que el grafo muera.

Para probar la falla de la API sin romper nada:
    ANTHROPIC_BASE_URL=http://localhost:9 python ejercicios/fase_8/ejercicio_3.py
Para probar la falla de la tool: pregunta por el pedido RP-9999 (simula un backend caído).
"""

import json
import operator
import re
from typing import Annotated, TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

load_dotenv()

# -------------------------------------------------------------------
# BLANK 1 — Reintentos y timeout en el cliente
# -------------------------------------------------------------------
# El cliente del SDK acepta dos parámetros de resiliencia:
#   max_retries → cuántas veces reintenta un error transitorio (por defecto 2)
#   timeout     → segundos máximos de espera por llamada (por defecto ~10 min, demasiado)
#
# 1a: número de reintentos (usa 3).   1b: segundos de timeout (usa 20).
#
# Pregunta para razonar: ¿por qué NO conviene reintentar un error 400 (petición mal formada)?
cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"},
    max_retries=___BLANK_1a___,
    timeout=___BLANK_1b___,
)

MODELO = "claude-sonnet-5"

# Tools con efectos reales: requieren aprobación humana antes de ejecutarse.
SENSIBLES = {"crear_reclamo"}

# Tope de tokens (entrada + salida) por conversación. Bájalo (p. ej. 1500) para probar el corte.
PRESUPUESTO_TOKENS = 6000


# -------------------------------------------------------------------
# Funciones simuladas y tools
# -------------------------------------------------------------------
def consultar_estado_pedido(numero_pedido: str) -> dict:
    if numero_pedido == "RP-9999":
        raise TimeoutError("El sistema de pedidos no responde")  # simula un backend caído
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
    6. Si una herramienta devuelve un error (argumentos inválidos o acción rechazada por un
       supervisor humano), no insistas con lo mismo: si el error es de formato, corrige el
       argumento o pídele el dato al usuario; si fue rechazada, explícale que no se pudo
       registrar y que un agente humano lo contactará.
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


class Estado(TypedDict):
    mensaje: str
    clasificacion: dict
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str
    aprobado: bool
    tokens_usados: Annotated[int, operator.add]


def tokens_de(respuesta) -> int:
    return respuesta.usage.input_tokens + respuesta.usage.output_tokens


def clasificar(estado: Estado) -> dict:
    previa = estado.get("clasificacion")
    contenido = f"Clasificación anterior: {previa}\nMensaje nuevo: {estado['mensaje']}"
    # El clasificador es "degradable": si falla, seguimos con una clasificación neutra y
    # dejamos que el ejecutor intente resolver (o falle con su propio mensaje).
    try:
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
    except (anthropic.APIError, ValueError, StopIteration) as e:
        print(f"  [clasificador] falló ({type(e).__name__}); uso clasificación neutra")
        return {"clasificacion": {"tipo": "otro", "numero_pedido": None}}
    print(f"  [clasificador] → {clasificacion}")
    return {"clasificacion": clasificacion, "tokens_usados": tokens_de(respuesta)}


# -------------------------------------------------------------------
# BLANK 2 — Que una falla de la API no tumbe el grafo
# -------------------------------------------------------------------
# Envuelve la llamada en try/except.
#   2a: qué clase de excepción capturar: la clase BASE de todos los errores del SDK de
#       Anthropic (red, 429, 5xx, timeout), dentro del módulo `anthropic`.
#   2b: en el except, devuelve un dict de state para que el grafo termine bien:
#         - "historial": UNA lista con un mensaje assistant de texto (`texto_falla`).
#           Sin esto el historial queda terminando en `user` y el siguiente turno falla.
#         - "stop_reason": "error"   (decidir lo manda a END, no es "tool_use")
#         - "respuesta": texto_falla
#
# Pregunta para razonar: ¿por qué se captura APIError aquí y no en el bucle principal?
def ejecutor(estado: Estado) -> dict:
    try:
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=1024,
            system=construir_system_ejecutor(estado["clasificacion"]),
            tools=tools,
            messages=estado["historial"],
        )
    except ___BLANK_2a___ as e:
        print(f"  [ejecutor] la API falló: {type(e).__name__}")
        texto_falla = "Tuve un problema técnico para responderte. Intenta de nuevo en un momento."
        return ___BLANK_2b___
    texto = next((b.text for b in respuesta.content if b.type == "text"), "")
    total = estado.get("tokens_usados", 0) + tokens_de(respuesta)
    print(f"  [ejecutor] stop_reason={respuesta.stop_reason} · tokens acumulados={total}/{PRESUPUESTO_TOKENS}")
    return {
        "historial": [{"role": "assistant", "content": bloques_a_dict(respuesta.content)}],
        "stop_reason": respuesta.stop_reason,
        "respuesta": texto,
        "tokens_usados": tokens_de(respuesta),
    }


def validar_argumentos(nombre: str, args: dict) -> str | None:
    numero = args.get("numero_pedido", "")
    if not re.fullmatch(r"RP-\d{4}", numero):
        return f"numero_pedido inválido: {numero!r}. El formato correcto es RP-1234."
    if nombre == "crear_reclamo" and not args.get("motivo", "").strip():
        return "El motivo del reclamo no puede estar vacío."
    return None


def requiere_aprobacion(bloque: dict) -> bool:
    """Una llamada pide aprobación humana solo si es sensible Y sus argumentos son válidos
    (no tiene sentido molestar al humano por una llamada que se va a rechazar igual)."""
    return (
        bloque["type"] == "tool_use"
        and bloque["name"] in SENSIBLES
        and validar_argumentos(bloque["name"], bloque["input"]) is None
    )


def aprobar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    acciones = [
        {"tool": b["name"], "argumentos": b["input"]}
        for b in ultimo["content"]
        if requiere_aprobacion(b)
    ]
    aprobado = interrupt(acciones)
    return {"aprobado": aprobado}


# -------------------------------------------------------------------
# BLANK 3 — Que una tool que falla no tumbe el grafo
# -------------------------------------------------------------------
# Envuelve la ejecución de la función en try/except Exception.
#   3a: en el `try`, ejecuta la función y agrega el tool_result normal (como antes).
#   3b: en el `except`, agrega un tool_result con `is_error: True` cuyo content explique el
#       fallo (usa el mensaje de la excepción `e`). Claude lo lee y se lo explica al usuario.
#
# Pregunta para razonar: ¿qué pasaría con el grafo si la excepción de `consultar_estado_pedido`
# (RP-9999) NO se capturara aquí?
def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    aprobado = estado.get("aprobado", False)
    resultados = []
    for bloque in ultimo["content"]:
        if bloque["type"] != "tool_use":
            continue
        error = validar_argumentos(bloque["name"], bloque["input"])
        if error:
            print(f"  [tools] {bloque['name']} INVÁLIDA: {error}")
            resultados.append({
                "type": "tool_result",
                "tool_use_id": bloque["id"],
                "content": error,
                "is_error": True,
            })
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
        try:
            ___BLANK_3a___
        except Exception as e:
            ___BLANK_3b___
    return {"historial": [{"role": "user", "content": resultados}]}


def limite(estado: Estado) -> dict:
    """Corta la conversación. Cierra el historial de forma válida: el último mensaje es un
    assistant con tool_use, así que hay que responder cada tool_use con un tool_result y
    luego añadir un assistant de texto. Si no, el siguiente turno da error 400."""
    ultimo = estado["historial"][-1]
    texto = "Alcanzamos el límite de esta conversación. Un agente humano te contactará."
    resultados = [
        {
            "type": "tool_result",
            "tool_use_id": b["id"],
            "content": "No ejecutada: se alcanzó el presupuesto de la conversación.",
            "is_error": True,
        }
        for b in ultimo["content"]
        if b["type"] == "tool_use"
    ]
    return {
        "historial": [
            {"role": "user", "content": resultados},
            {"role": "assistant", "content": [{"type": "text", "text": texto}]},
        ],
        "stop_reason": "limite",
        "respuesta": texto,
    }


def decidir(estado: Estado) -> str:
    if estado["stop_reason"] != "tool_use":
        return END
    if estado.get("tokens_usados", 0) > PRESUPUESTO_TOKENS:
        return "limite"
    ultimo = estado["historial"][-1]
    if any(requiere_aprobacion(b) for b in ultimo["content"]):
        return "aprobar"
    return "tools"


builder = StateGraph(Estado)
builder.add_node("clasificar", clasificar)
builder.add_node("ejecutor", ejecutor)
builder.add_node("aprobar", aprobar)
builder.add_node("tools", tools_node)
builder.add_node("limite", limite)

builder.add_edge(START, "clasificar")
builder.add_edge("clasificar", "ejecutor")
builder.add_conditional_edges(
    "ejecutor",
    decidir,
    {"limite": "limite", "aprobar": "aprobar", "tools": "tools", END: END},
)
builder.add_edge("aprobar", "tools")
builder.add_edge("tools", "ejecutor")
builder.add_edge("limite", END)

memoria = MemorySaver()
grafo = builder.compile(checkpointer=memoria)


print("Agente robusto — 'nuevo' otra conversación, 'salir' termina\n")

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

    config = {"configurable": {"thread_id": f"conversacion-{contador_hilos}"}, "recursion_limit": 15}

    print()
    try:
        resultado = grafo.invoke(
            {"mensaje": user_input, "historial": [{"role": "user", "content": user_input}]},
            config,
        )
        while "__interrupt__" in resultado:
            acciones = resultado["__interrupt__"][0].value
            print("\n⏸  Acción pendiente de aprobación:")
            for a in acciones:
                print(f"   - {a['tool']}({a['argumentos']})")
            decision = input("¿Aprobar? (s/n): ").strip().lower() == "s"
            print()
            resultado = grafo.invoke(Command(resume=decision), config)
        print(f"\nAgente: {resultado['respuesta']}\n")
    except GraphRecursionError:
        print("\nAgente: Lo siento, no pude completar tu solicitud. Un agente humano te contactará.\n")
