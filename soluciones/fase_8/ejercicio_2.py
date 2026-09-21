"""
Fase 8 — Ejercicio 2: Guardrails (validar argumentos y presupuesto de tokens)
=============================================================================
Objetivo: poner límites al agente ANTES de que haga daño, sin depender de que el modelo
se porte bien.

Al ejercicio 1 (aprobación humana, ya resuelta aquí) le sumamos dos guardrails:

  1. VALIDACIÓN DE ARGUMENTOS: Claude puede inventar o malformar argumentos
     (`numero_pedido="el de ayer"`). Se validan en código antes de ejecutar la tool. Si
     son inválidos, se devuelve un `tool_result` con `is_error: True` y Claude puede
     corregirse. Además, una llamada inválida NO debe molestar al humano: se valida
     antes de pedir aprobación.
  2. PRESUPUESTO DE TOKENS: cada conversación (thread) acumula los tokens gastados. Si
     pasa del tope, el agente corta con un mensaje en vez de seguir gastando.

Conceptos nuevos:
  - `response.usage.input_tokens` / `output_tokens`: cuántos tokens costó cada llamada.
  - Reducer para CONTADORES: `Annotated[int, operator.add]` suma lo que devuelve cada nodo.
  - `is_error: True` en un tool_result: le dice a Claude que la tool falló.
  - Un `tool_use` SIEMPRE necesita su `tool_result` en el historial. Si cortas el flujo
    sin responderlo, el siguiente turno da error 400. Por eso el nodo `limite` cierra
    el historial correctamente.

Flujo:
    START → clasificar → ejecutor ─┬─ (presupuesto excedido) → limite → END
                                   ├─ (tool sensible válida) → aprobar → tools → ejecutor
                                   ├─ (tool segura o inválida) ─────────→ tools → ejecutor
                                   └─ (sin tools) → END
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

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
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


# -------------------------------------------------------------------
# BLANK 1 — Un contador en el State
# -------------------------------------------------------------------
# Agrega el campo `tokens_usados`: un entero que se ACUMULA entre nodos y turnos.
# Cada nodo devolverá solo los tokens de SU llamada y LangGraph los suma.
#
# Pista: ¿qué reducer suma? Ya lo usaste con listas en `historial`; funciona igual con int.
#
# Pregunta para razonar: ¿por qué un contador sin reducer NO sirve aquí?
class Estado(TypedDict):
    mensaje: str
    clasificacion: dict
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str
    aprobado: bool
    tokens_usados: Annotated[int, operator.add]


# -------------------------------------------------------------------
# BLANK 2 — Medir lo que cuesta cada llamada
# -------------------------------------------------------------------
# Toda respuesta del SDK trae `respuesta.usage` con `input_tokens` y `output_tokens`.
# Escribe el cuerpo de `tokens_de`: devuelve el total (entrada + salida) de esa llamada.
def tokens_de(respuesta) -> int:
    return respuesta.usage.input_tokens + respuesta.usage.output_tokens


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
    return {"clasificacion": clasificacion, "tokens_usados": tokens_de(respuesta)}


def ejecutor(estado: Estado) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=1024,
        system=construir_system_ejecutor(estado["clasificacion"]),
        tools=tools,
        messages=estado["historial"],
    )
    texto = next((b.text for b in respuesta.content if b.type == "text"), "")
    total = estado.get("tokens_usados", 0) + tokens_de(respuesta)
    print(f"  [ejecutor] stop_reason={respuesta.stop_reason} · tokens acumulados={total}/{PRESUPUESTO_TOKENS}")
    return {
        "historial": [{"role": "assistant", "content": bloques_a_dict(respuesta.content)}],
        "stop_reason": respuesta.stop_reason,
        "respuesta": texto,
        "tokens_usados": tokens_de(respuesta),
    }


# -------------------------------------------------------------------
# BLANK 3 — Validar argumentos en código
# -------------------------------------------------------------------
# `validar_argumentos` devuelve un mensaje de error (str) si algo está mal, o None si todo
# está bien. Un número de pedido válido tiene la forma "RP-" + 4 dígitos (RP-1001).
#
# Completa la condición del `if`: debe ser verdadera cuando `numero` NO cumple el formato.
# Pista: `re.fullmatch(patrón, texto)` devuelve None si el texto no coincide COMPLETO
#        con el patrón. Patrón: r"RP-\d{4}".
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
# BLANK 4 — Rechazar argumentos inválidos sin ejecutar
# -------------------------------------------------------------------
# En `tools_node`, ANTES de ejecutar cada tool:
#   4a: guarda en `error` lo que devuelve `validar_argumentos` (recibe nombre e input del bloque).
#   4b: si hay error, el tool_result debe llevar: type "tool_result", tool_use_id del bloque,
#       content = el mensaje de error, e `is_error: True`. Así Claude sabe que falló y puede
#       corregirse. Escribe ese dict.
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
        resultado = FUNCIONES[bloque["name"]](**bloque["input"])
        resultados.append({
            "type": "tool_result",
            "tool_use_id": bloque["id"],
            "content": json.dumps(resultado),
        })
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


# -------------------------------------------------------------------
# BLANK 5 — Cortar cuando se pasa el presupuesto
# -------------------------------------------------------------------
# 5a: en `decidir`, después de comprobar que Claude quiere usar tools, devuelve "limite" si
#     los tokens acumulados superan PRESUPUESTO_TOKENS. Completa la condición del `if`.
#     (Usa estado.get("tokens_usados", 0).)
# 5b: en add_conditional_edges, el mapa debe incluir la nueva salida "limite", además de
#     "aprobar", "tools" y END.
#
# Pregunta para razonar: ¿por qué se comprueba el presupuesto DESPUÉS de que el ejecutor
# gastó los tokens y no antes de llamarlo?
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


print("Agente con guardrails — 'nuevo' otra conversación, 'salir' termina\n")

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
