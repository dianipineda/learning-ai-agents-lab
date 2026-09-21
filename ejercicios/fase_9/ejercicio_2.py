"""
Fase 9 — Ejercicio 2: Supervisor y traspasos (handoff) entre agentes especializados
==================================================================================
Objetivo: pasar de UN agente que hace todo a un EQUIPO de agentes especializados
(pedidos, reclamos, pagos), coordinado por un supervisor.

Arquitectura:

    START → supervisor → especialista ⇄ tools
                              │
                              └→ traspasar → especialista   (con otro agente activo)
                              │
                              └→ END

  - SUPERVISOR: lee el mensaje y elige el agente inicial. Usamos `tool_choice` para OBLIGAR
    a Claude a llamar la tool `elegir_agente`: así la salida es un dato estructurado y no
    hay que parsear texto.
  - ESPECIALISTA: un solo nodo que actúa como el agente indicado en `estado["agente"]`:
    cada agente es un system prompt + un subconjunto de tools (ver AGENTES). Cambiar de
    agente es solo cambiar ese campo del state.
  - TRASPASO (handoff): un agente puede llamar la tool `transferir_a(agente, motivo)`. El nodo
    `traspasar` responde esa llamada (todo tool_use necesita su tool_result), cambia el agente
    activo y el historial COMPARTIDO permite que el nuevo agente continúe sin repreguntar.
  - GUARDA: máximo MAX_TRASPASOS por conversación, para que dos agentes no se pasen al
    usuario en bucle.

Cada mensaje se procesa como una conversación independiente (sin memoria entre mensajes;
la memoria con checkpointer ya la practicaste en las fases 7 y 8).
"""

import operator
from typing import Annotated, TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

MODELO = "claude-sonnet-5"

# Cuántos traspasos (handoffs) entre agentes permitimos por conversación. Evita que dos
# agentes se pasen el usuario de ida y vuelta para siempre.
MAX_TRASPASOS = 2


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


def consultar_pago(numero_pedido: str) -> dict:
    pagos_simulados = {
        "RP-1001": {"cobros": 2, "monto_por_cobro": 35000, "estado_pago": "cobro_duplicado"},
        "RP-1002": {"cobros": 1, "monto_por_cobro": 28000, "estado_pago": "pagado"},
        "RP-1003": {"cobros": 1, "monto_por_cobro": 41000, "estado_pago": "pagado"},
    }
    return pagos_simulados.get(numero_pedido, {"cobros": 0, "estado_pago": "no_encontrado"})


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


FUNCIONES = {
    "consultar_estado_pedido": consultar_estado_pedido,
    "consultar_pago": consultar_pago,
    "crear_reclamo": crear_reclamo,
}

_PEDIDO = {"numero_pedido": {"type": "string", "description": "Ej: 'RP-1001'"}}
TOOLS = [
    {
        "name": "consultar_estado_pedido",
        "description": "Consulta el estado actual de un pedido dado su número.",
        "input_schema": {"type": "object", "properties": _PEDIDO, "required": ["numero_pedido"]},
    },
    {
        "name": "consultar_pago",
        "description": "Consulta los cobros registrados de un pedido (cuántos y de cuánto).",
        "input_schema": {"type": "object", "properties": _PEDIDO, "required": ["numero_pedido"]},
    },
    {
        "name": "crear_reclamo",
        "description": "Registra un reclamo formal sobre un pedido. Requiere número de pedido y motivo.",
        "input_schema": {
            "type": "object",
            "properties": {**_PEDIDO, "motivo": {"type": "string", "description": "Resumen breve del problema"}},
            "required": ["numero_pedido", "motivo"],
        },
    },
]

# -------------------------------------------------------------------
# Agentes especializados: cada uno = un system prompt + un subconjunto de tools.
# Todos comparten además la tool `transferir_a` para pasarle la conversación a otro.
# -------------------------------------------------------------------
AGENTES = {
    "pedidos": {
        "tools": ["consultar_estado_pedido"],
        "system": """
Eres el agente de PEDIDOS de Rappi. Amable y breve. Solo consultas el estado de pedidos con
consultar_estado_pedido. Si falta el número de pedido, pídeselo al usuario.
Si el usuario quiere reportar un problema o reclamar, usa transferir_a('reclamos').
Si pregunta por cobros o pagos, usa transferir_a('pagos').
Nunca inventes datos ni prometas nada que las herramientas no confirmen.
""",
    },
    "reclamos": {
        "tools": ["consultar_estado_pedido", "crear_reclamo"],
        "system": """
Eres el agente de RECLAMOS de Rappi. Amable y breve. Para registrar un reclamo: primero
consulta el pedido con consultar_estado_pedido y luego usa crear_reclamo. Empieza con una
disculpa sincera y entrega el ID del reclamo. Si falta el número de pedido, pídeselo antes.
Si la consulta es sobre cobros o pagos y no sobre un problema para reclamar, usa transferir_a('pagos').
Si una herramienta devuelve un error, no insistas: explícale al usuario lo que pasó.
Nunca inventes datos ni prometas nada que las herramientas no confirmen.
""",
    },
    "pagos": {
        "tools": ["consultar_pago"],
        "system": """
Eres el agente de PAGOS de Rappi. Amable y breve. Consultas cobros con consultar_pago. Si falta
el número de pedido, pídeselo. Si detectas un cobro duplicado, explícalo con claridad y, si el
usuario quiere reclamar o pide que se registre, usa transferir_a('reclamos') indicando el motivo.
Nunca inventes datos ni prometas reembolsos: solo puedes consultar cobros.
""",
    },
}

TRANSFERIR = {
    "name": "transferir_a",
    "description": (
        "Traspasa la conversación a otro agente especializado cuando el tema del usuario "
        "corresponde a él. Indica el motivo y lo que ya sabes, para que no tenga que repreguntar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agente": {"type": "string", "enum": list(AGENTES)},
            "motivo": {"type": "string", "description": "Por qué se traspasa y qué contexto ya hay"},
        },
        "required": ["agente", "motivo"],
    },
}

SYSTEM_SUPERVISOR = """
Eres el supervisor de un equipo de soporte de pedidos de Rappi. Lee el mensaje del cliente y elige
qué agente debe atenderlo:
- pedidos: estado o ubicación de un pedido, saludos y cualquier consulta general.
- reclamos: el cliente reporta un problema (frío, incompleto, demora) o quiere reclamar.
- pagos: preguntas sobre cobros, cargos duplicados o pagos.
Usa siempre la herramienta elegir_agente.
"""

ELEGIR_AGENTE = {
    "name": "elegir_agente",
    "description": "Elige el agente especialista que debe atender el mensaje del cliente.",
    "input_schema": {
        "type": "object",
        "properties": {"agente": {"type": "string", "enum": list(AGENTES)}},
        "required": ["agente"],
    },
}


def bloques_a_dict(content) -> list[dict]:
    """Convierte los bloques del SDK en dicts simples (serializables por el checkpointer)."""
    salida = []
    for b in content:
        if b.type == "text":
            salida.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            salida.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return salida


def responder_llamadas(ultimo: dict, traspaso_id: str, texto: str, es_error: bool) -> list[dict]:
    """Un tool_use SIEMPRE necesita su tool_result. Responde el traspaso con `texto` y marca
    cualquier otra llamada del mismo turno como no ejecutada."""
    resultados = []
    for b in ultimo["content"]:
        if b["type"] != "tool_use":
            continue
        if b["id"] == traspaso_id:
            resultados.append({"type": "tool_result", "tool_use_id": b["id"], "content": texto, "is_error": es_error})
        else:
            resultados.append({
                "type": "tool_result",
                "tool_use_id": b["id"],
                "content": "No ejecutada: hubo un traspaso en el mismo turno. Vuelve a pedirla si aún hace falta.",
                "is_error": True,
            })
    return resultados


class Estado(TypedDict):
    mensaje: str
    agente: str                                  # especialista activo
    historial: Annotated[list, operator.add]     # historial COMPARTIDO por todos los agentes
    stop_reason: str
    respuesta: str
    traza: Annotated[list, operator.add]         # agentes por los que pasó la conversación
    traspasos: Annotated[int, operator.add]      # contador de traspasos


# -------------------------------------------------------------------
# BLANK 1 y 2 — El supervisor elige al agente inicial
# -------------------------------------------------------------------
# 1: `tool_choice` obliga a Claude a usar UNA tool concreta. Su formato es un dict:
#      {"type": "tool", "name": "<nombre de la tool>"}      → la tool es `elegir_agente`.
# 2: la respuesta trae un bloque `tool_use`; su `.input` es un dict con la clave "agente".
#    Extrae el nombre del agente elegido de ese bloque.
#
# Pregunta para razonar: ¿qué ventaja tiene forzar una tool frente a pedirle a Claude "responde
# solo con el nombre del agente" y leer el texto?
def supervisor(estado: Estado) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=SYSTEM_SUPERVISOR,
        tools=[ELEGIR_AGENTE],
        tool_choice=___BLANK_1___,
        messages=[{"role": "user", "content": estado["mensaje"]}],
    )
    agente = ___BLANK_2___
    print(f"  [supervisor] → {agente}")
    return {"agente": agente, "traza": [agente]}


# -------------------------------------------------------------------
# BLANK 3 — Cada especialista usa SU prompt
# -------------------------------------------------------------------
# 3: el `system` debe ser el de `nombre` (el agente activo), guardado en AGENTES[nombre]["system"].
#
# Las tools ya están filtradas: cada agente solo ve las suyas + `transferir_a`. Es un guardrail:
# el agente de pagos no puede crear reclamos aunque quiera.
def especialista(estado: Estado) -> dict:
    nombre = estado["agente"]
    herramientas = [t for t in TOOLS if t["name"] in AGENTES[nombre]["tools"]] + [TRANSFERIR]
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=1024,
        system=___BLANK_3___,
        tools=herramientas,
        messages=estado["historial"],
    )
    texto = next((b.text for b in respuesta.content if b.type == "text"), "")
    print(f"  [{nombre}] stop_reason={respuesta.stop_reason}")
    return {
        "historial": [{"role": "assistant", "content": bloques_a_dict(respuesta.content)}],
        "stop_reason": respuesta.stop_reason,
        "respuesta": texto,
    }


def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    resultados = []
    for bloque in ultimo["content"]:
        if bloque["type"] != "tool_use":
            continue
        print(f"  [tools] {bloque['name']}({bloque['input']})")
        try:
            resultado = FUNCIONES[bloque["name"]](**bloque["input"])
            resultados.append({"type": "tool_result", "tool_use_id": bloque["id"], "content": str(resultado)})
        except Exception as e:
            resultados.append({
                "type": "tool_result",
                "tool_use_id": bloque["id"],
                "content": f"La herramienta falló: {e}",
                "is_error": True,
            })
    return {"historial": [{"role": "user", "content": resultados}]}


# -------------------------------------------------------------------
# BLANK 4 — El nodo de traspaso
# -------------------------------------------------------------------
# 4a: condición para RECHAZAR el traspaso: ya se agotó MAX_TRASPASOS (usa estado.get("traspasos", 0))
#     O el destino es el mismo agente que ya está activo.
#     Si se rechaza, el agente actual sigue con la conversación y recibe un error legible.
# 4b: si se acepta, el nuevo agente activo es `destino`.
def traspasar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    pedido = next(b for b in ultimo["content"] if b["type"] == "tool_use" and b["name"] == "transferir_a")
    destino = pedido["input"]["agente"]
    motivo = pedido["input"].get("motivo", "")

    if ___BLANK_4a___:
        print(f"  [traspaso] a {destino} RECHAZADO")
        texto = "Traspaso rechazado. Resuelve tú con tus herramientas o explícale al usuario lo que no puedes hacer."
        return {"historial": [{"role": "user", "content": responder_llamadas(ultimo, pedido["id"], texto, True)}]}

    print(f"  [traspaso] {estado['agente']} → {destino} (motivo: {motivo})")
    texto = f"Traspaso a '{destino}' realizado. Motivo: {motivo}. Continúa tú atendiendo al usuario."
    return {
        "historial": [{"role": "user", "content": responder_llamadas(ultimo, pedido["id"], texto, False)}],
        "agente": ___BLANK_4b___,
        "traza": [destino],
        "traspasos": 1,
    }


# -------------------------------------------------------------------
# BLANK 5 — ¿Traspaso, herramienta o fin?
# -------------------------------------------------------------------
# 5: `hay_traspaso` es True si algún bloque del último mensaje es un tool_use llamado "transferir_a".
#    Los traspasos tienen prioridad sobre las demás tools del mismo turno.
def decidir(estado: Estado) -> str:
    if estado["stop_reason"] != "tool_use":
        return END
    ultimo = estado["historial"][-1]
    hay_traspaso = ___BLANK_5___
    return "traspasar" if hay_traspaso else "tools"


# -------------------------------------------------------------------
# BLANK 6 y 7 — El grafo
# -------------------------------------------------------------------
# 6: el mapa de rutas de `decidir`: "traspasar" → nodo traspasar, "tools" → nodo tools, END → END.
# 7: la arista que devuelve el control al especialista tras un traspaso (como tools → especialista).
builder = StateGraph(Estado)
builder.add_node("supervisor", supervisor)
builder.add_node("especialista", especialista)
builder.add_node("tools", tools_node)
builder.add_node("traspasar", traspasar)

builder.add_edge(START, "supervisor")
builder.add_edge("supervisor", "especialista")
builder.add_conditional_edges(
    "especialista",
    decidir,
    ___BLANK_6___,
)
builder.add_edge("tools", "especialista")
___BLANK_7___

grafo = builder.compile()


print("Equipo de soporte (supervisor + pedidos/reclamos/pagos) — 'salir' termina\n")

while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir":
        print("¡Hasta luego!")
        break
    print()
    try:
        resultado = grafo.invoke(
            {"mensaje": user_input, "historial": [{"role": "user", "content": user_input}]},
            {"recursion_limit": 25},
        )
        print(f"\nRuta: {' → '.join(resultado['traza'])}")
        print(f"Agente: {resultado['respuesta']}\n")
    except GraphRecursionError:
        print("\nAgente: Lo siento, no pude completar tu solicitud. Un agente humano te contactará.\n")
