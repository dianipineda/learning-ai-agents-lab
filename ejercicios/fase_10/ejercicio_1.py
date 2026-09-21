"""
Fase 10 — Proyecto final, parte 1: el orquestador
=================================================
Objetivo: ensamblar en UN solo agente todo lo aprendido. Aquí no hay conceptos nuevos: cada
pieza ya la construiste por separado; el reto es que convivan sin pisarse.

  Fase 7  → grafo de LangGraph, estado con reducers, checkpointer (memoria por hilo).
  Fase 8  → aprobación humana (`interrupt`), validación de argumentos, presupuesto de tokens,
            reintentos/timeouts, errores de API y de tools que no tumban el grafo.
  Fase 9  → supervisor que enruta + especialistas (pedidos / reclamos / pagos) con traspasos.

Lo que SÍ es nuevo es lo que aparece al juntar todo:
  - MEMORIA POR HILO + SUPERVISOR: el estado ahora vive entre mensajes. El supervisor decide en
    cada turno (ve qué agente venía atendiendo) y hay contadores que deben REINICIARSE por turno
    (traspasos, aprobación) mientras otros deben ACUMULARSE por conversación (tokens, historial).
  - ORDEN DE LAS DECISIONES en `decidir`: presupuesto → traspaso → aprobación → tools.
  - CIERRE DE HILOS ROTOS: si el grafo se corta a medias (GraphRecursionError) el historial
    guardado puede quedar con un tool_use sin su tool_result; el siguiente mensaje daría error 400.
    Es el edge case pendiente de la fase 7: aquí se repara.

Flujo:
    START → supervisor → especialista ─┬─ (fin) ─────────────────────→ END
                              ▲        ├─ (presupuesto excedido) → limite → END
                              │        ├─ (transferir_a) → traspasar ─┐
                              │        ├─ (tool sensible válida) → aprobar → tools ─┐
                              │        └─ (tool segura o inválida) ──→ tools ───────┤
                              └────────────────────────────────────────────────────┘

Ejecutar (desde la raíz del repo):
    python ejercicios/fase_10/ejercicio_1.py
Comandos: 'nuevo' abre otra conversación (otro hilo), 'salir' termina.
La evaluación final (ejercicio 2) importa este archivo, así que resuélvelo primero.
"""

import json
import operator
import re
import uuid
from typing import Annotated, TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"},
    max_retries=3,
    timeout=20.0,
)

MODELO = "claude-sonnet-5"

# Tools con efectos reales: requieren aprobación humana antes de ejecutarse.
SENSIBLES = {"crear_reclamo"}

# Tope de tokens (entrada + salida) por CONVERSACIÓN (hilo). Con memoria por hilo se acumula
# entre mensajes. Es un valor inicial: ajústalo con la API real (ejercicio 2).
PRESUPUESTO_TOKENS = 12000

# Traspasos permitidos por MENSAJE del usuario (se reinicia en cada turno).
MAX_TRASPASOS = 2

TEXTO_FALLA = "Tuve un problema técnico para responderte. Intenta de nuevo en un momento."
TEXTO_CORTE = "Alcanzamos el límite de esta conversación. Un agente humano te contactará."


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
# Agentes especializados: un system prompt + un subconjunto de tools cada uno.
# Todos comparten además `transferir_a` para pasarle la conversación a otro.
# -------------------------------------------------------------------
AGENTES = {
    "pedidos": {
        "tools": ["consultar_estado_pedido"],
        "system": """
Eres el agente de PEDIDOS de Rappi. Amable y breve. Solo consultas el estado de pedidos con
consultar_estado_pedido. Si falta el número de pedido, pídeselo al usuario.
Si el usuario quiere reportar un problema o reclamar, usa transferir_a('reclamos').
Si pregunta por cobros o pagos, usa transferir_a('pagos').
Si una herramienta devuelve un error, no insistas: explícale al usuario lo que pasó.
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
Si una herramienta devuelve un error (argumentos inválidos, acción rechazada por un supervisor
humano o sistema caído), no insistas con lo mismo: corrige el argumento o pídele el dato al
usuario; si fue rechazada, explícale que no se pudo registrar y que un agente humano lo contactará.
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
Eres el supervisor de un equipo de soporte de pedidos de Rappi. Lee el mensaje nuevo del cliente
y elige qué agente debe atenderlo:
- pedidos: estado o ubicación de un pedido, saludos y cualquier consulta general.
- reclamos: el cliente reporta un problema (frío, incompleto, demora) o quiere reclamar.
- pagos: preguntas sobre cobros, cargos duplicados o pagos.
Se te indica qué agente venía atendiendo la conversación. Si el mensaje es un seguimiento (por
ejemplo, solo trae el número de pedido que faltaba), conserva ese agente.
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


# -------------------------------------------------------------------
# Utilidades (ya resueltas en fases anteriores)
# -------------------------------------------------------------------
def bloques_a_dict(content) -> list[dict]:
    """Convierte los bloques del SDK en dicts simples (serializables por el checkpointer)."""
    salida = []
    for b in content:
        if b.type == "text":
            salida.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            salida.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return salida


def tokens_de(respuesta) -> int:
    return respuesta.usage.input_tokens + respuesta.usage.output_tokens


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


def validar_argumentos(nombre: str, args: dict) -> str | None:
    """Devuelve un mensaje de error si los argumentos son inválidos, o None si están bien."""
    numero = args.get("numero_pedido", "")
    if not re.fullmatch(r"RP-\d{4}", numero):
        return f"numero_pedido inválido: {numero!r}. El formato correcto es RP-1234."
    if nombre == "crear_reclamo" and not args.get("motivo", "").strip():
        return "El motivo del reclamo no puede estar vacío."
    return None


def requiere_aprobacion(bloque: dict) -> bool:
    """Pide aprobación humana solo si la tool es sensible Y sus argumentos son válidos
    (no tiene sentido molestar al humano por una llamada que se va a rechazar igual)."""
    return (
        bloque["type"] == "tool_use"
        and bloque["name"] in SENSIBLES
        and validar_argumentos(bloque["name"], bloque["input"]) is None
    )


# -------------------------------------------------------------------
# BLANK 1 — Qué se acumula y qué se reinicia
# -------------------------------------------------------------------
# Con memoria por hilo, el estado sobrevive entre mensajes. Por eso cada campo necesita una
# política clara:
#   historial, traza     → se ACUMULAN (reducer de listas, ya lo tienes)
#   traspasos, aprobado  → se REINICIAN en cada turno (sin reducer: el supervisor los pone en 0/False)
#   tokens_usados        → se ACUMULA por conversación (es el presupuesto del hilo)
# 1: escribe el tipo de `tokens_usados` para que se sume entre nodos y turnos.
#
# Pregunta para razonar: si `traspasos` tuviera reducer de suma, ¿qué pasaría en el turno 3
# de una conversación en la que ya hubo dos traspasos?
class Estado(TypedDict):
    mensaje: str
    agente: str
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str
    traza: Annotated[list, operator.add]
    traspasos: int
    aprobado: bool
    tokens_usados: ___BLANK_1___


def supervisor(estado: Estado) -> dict:
    previo = estado.get("agente")
    contenido = f"Agente que venía atendiendo: {previo or 'ninguno'}\nMensaje nuevo: {estado['mensaje']}"
    try:
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=256,
            system=SYSTEM_SUPERVISOR,
            tools=[ELEGIR_AGENTE],
            tool_choice={"type": "tool", "name": "elegir_agente"},
            messages=[{"role": "user", "content": contenido}],
        )
        agente = next(b for b in respuesta.content if b.type == "tool_use").input["agente"]
        tokens = tokens_de(respuesta)
    except (anthropic.APIError, StopIteration) as e:
        # El supervisor es "degradable": si falla, seguimos con el agente previo (o pedidos).
        print(f"  [supervisor] falló ({type(e).__name__}); uso {previo or 'pedidos'}")
        agente, tokens = previo or "pedidos", 0
    print(f"  [supervisor] → {agente}")
    # -------------------------------------------------------------------
    # BLANK 2 — El estado con el que arranca CADA turno
    # -------------------------------------------------------------------
    # 2: devuelve un dict con: "agente" (el elegido), "traza" (lista con ese agente),
    #    "tokens_usados" (los tokens de esta llamada), y además REINICIA las dos políticas
    #    por turno: "traspasos" a 0 y "aprobado" a False (fail closed: ninguna aprobación de un
    #    turno anterior debe valer en el siguiente).
    return ___BLANK_2___


# -------------------------------------------------------------------
# BLANK 3 — Que una falla de la API no tumbe el grafo
# -------------------------------------------------------------------
# 3: en el `except`, devuelve el dict que termina bien el turno:
#      - "historial": UNA lista con un mensaje assistant de texto (TEXTO_FALLA). Sin él el
#        historial acaba en `user` y el siguiente turno del hilo daría error 400.
#      - "stop_reason": "error"   (decidir lo manda a END)
#      - "respuesta": TEXTO_FALLA
def especialista(estado: Estado) -> dict:
    nombre = estado["agente"]
    herramientas = [t for t in TOOLS if t["name"] in AGENTES[nombre]["tools"]] + [TRANSFERIR]
    try:
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=1024,
            system=AGENTES[nombre]["system"],
            tools=herramientas,
            messages=estado["historial"],
        )
    except anthropic.APIError as e:
        print(f"  [{nombre}] la API falló: {type(e).__name__}")
        return ___BLANK_3___
    texto = next((b.text for b in respuesta.content if b.type == "text"), "")
    total = estado.get("tokens_usados", 0) + tokens_de(respuesta)
    print(f"  [{nombre}] stop_reason={respuesta.stop_reason} · tokens acumulados={total}/{PRESUPUESTO_TOKENS}")
    return {
        "historial": [{"role": "assistant", "content": bloques_a_dict(respuesta.content)}],
        "stop_reason": respuesta.stop_reason,
        "respuesta": texto,
        "tokens_usados": tokens_de(respuesta),
    }


def aprobar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    acciones = [
        {"tool": b["name"], "argumentos": b["input"]}
        for b in ultimo["content"]
        if requiere_aprobacion(b)
    ]
    aprobado = interrupt(acciones)
    return {"aprobado": aprobado}


def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    aprobado = estado.get("aprobado", False)  # fail closed
    resultados = []
    for bloque in ultimo["content"]:
        if bloque["type"] != "tool_use":
            continue
        error = validar_argumentos(bloque["name"], bloque["input"])
        if error:
            print(f"  [tools] {bloque['name']} INVÁLIDA: {error}")
            resultados.append({"type": "tool_result", "tool_use_id": bloque["id"], "content": error, "is_error": True})
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
            resultado = FUNCIONES[bloque["name"]](**bloque["input"])
            resultados.append({"type": "tool_result", "tool_use_id": bloque["id"], "content": json.dumps(resultado)})
        except Exception as e:
            print(f"  [tools] {bloque['name']} FALLÓ: {type(e).__name__}: {e}")
            resultados.append({
                "type": "tool_result",
                "tool_use_id": bloque["id"],
                "content": f"La herramienta falló: {e}. No se pudo completar la acción.",
                "is_error": True,
            })
    return {"historial": [{"role": "user", "content": resultados}]}


def traspasar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    pedido = next(b for b in ultimo["content"] if b["type"] == "tool_use" and b["name"] == "transferir_a")
    destino = pedido["input"]["agente"]
    motivo = pedido["input"].get("motivo", "")
    hechos = estado.get("traspasos", 0)
    if hechos >= MAX_TRASPASOS or destino == estado["agente"]:
        print(f"  [traspaso] a {destino} RECHAZADO")
        texto = "Traspaso rechazado. Resuelve tú con tus herramientas o explícale al usuario lo que no puedes hacer."
        return {"historial": [{"role": "user", "content": responder_llamadas(ultimo, pedido["id"], texto, True)}]}
    print(f"  [traspaso] {estado['agente']} → {destino} (motivo: {motivo})")
    texto = f"Traspaso a '{destino}' realizado. Motivo: {motivo}. Continúa tú atendiendo al usuario."
    return {
        "historial": [{"role": "user", "content": responder_llamadas(ultimo, pedido["id"], texto, False)}],
        "agente": destino,
        "traza": [destino],
        "traspasos": hechos + 1,
    }


def limite(estado: Estado) -> dict:
    """Corta la conversación cerrando el historial de forma válida: cada tool_use del último
    mensaje recibe su tool_result y luego un assistant de texto."""
    ultimo = estado["historial"][-1]
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
            {"role": "assistant", "content": [{"type": "text", "text": TEXTO_CORTE}]},
        ],
        "stop_reason": "limite",
        "respuesta": TEXTO_CORTE,
    }


# -------------------------------------------------------------------
# BLANK 4 — El orden de las decisiones
# -------------------------------------------------------------------
# `decidir` va comprobando de lo más urgente a lo menos:
#   4a: si los tokens acumulados superan PRESUPUESTO_TOKENS → "limite" (usa estado.get(..., 0)).
#   4b: si alguna llamada del último mensaje requiere aprobación (`requiere_aprobacion`) → "aprobar".
# Ya está el traspaso. Ojo al ORDEN: el presupuesto va primero porque `limite` responde TODOS los
# tool_use, incluido un `transferir_a` pendiente; si el traspaso fuera antes, un hilo sin
# presupuesto podría seguir pasándose el usuario de un agente a otro.
#
# Pregunta para razonar: ¿por qué "aprobar" va antes que "tools"?
def decidir(estado: Estado) -> str:
    if estado["stop_reason"] != "tool_use":
        return END
    if ___BLANK_4a___:
        return "limite"
    ultimo = estado["historial"][-1]
    if any(b["type"] == "tool_use" and b["name"] == "transferir_a" for b in ultimo["content"]):
        return "traspasar"
    if ___BLANK_4b___:
        return "aprobar"
    return "tools"


# -------------------------------------------------------------------
# BLANK 5 — El grafo completo
# -------------------------------------------------------------------
# 5: el mapa de rutas de `decidir`: limite, traspasar, aprobar, tools y END (cada nombre a su nodo).
# 6: compila con un checkpointer en memoria. Sin él no hay `interrupt` ni memoria entre mensajes.
#
# Pregunta para razonar: ¿qué se pierde si en producción usas MemorySaver y el proceso se reinicia?
builder = StateGraph(Estado)
builder.add_node("supervisor", supervisor)
builder.add_node("especialista", especialista)
builder.add_node("aprobar", aprobar)
builder.add_node("tools", tools_node)
builder.add_node("traspasar", traspasar)
builder.add_node("limite", limite)

builder.add_edge(START, "supervisor")
builder.add_edge("supervisor", "especialista")
builder.add_conditional_edges(
    "especialista",
    decidir,
    ___BLANK_5___,
)
builder.add_edge("aprobar", "tools")
builder.add_edge("tools", "especialista")
builder.add_edge("traspasar", "especialista")
builder.add_edge("limite", END)

grafo = builder.compile(checkpointer=___BLANK_6___)


# -------------------------------------------------------------------
# BLANK 7 — Reparar un hilo roto
# -------------------------------------------------------------------
# Si el grafo se corta por GraphRecursionError, el último mensaje guardado puede ser un assistant
# con tool_use SIN tool_result. Cualquier mensaje nuevo en ese hilo daría error 400.
# `cerrar_hilo` lo repara con `grafo.update_state(...)`, que escribe en el hilo como si lo hubiera
# hecho el nodo `as_node="limite"` (así el grafo queda terminado, sin nodos pendientes).
# 7: la lista `resultados`: un tool_result por cada tool_use de `usos`, con "type", "tool_use_id",
#    "content" (un texto que diga que no se ejecutó) e "is_error": True.
def cerrar_hilo(config: dict) -> None:
    historial = grafo.get_state(config).values.get("historial", [])
    if not historial:
        return
    ultimo = historial[-1]
    cierre = {"role": "assistant", "content": [{"type": "text", "text": TEXTO_CORTE}]}
    if ultimo["role"] == "assistant":
        usos = [b for b in ultimo["content"] if b["type"] == "tool_use"]
        if not usos:
            return  # ya termina en texto: el hilo está bien formado
        resultados = ___BLANK_7___
        nuevos = [{"role": "user", "content": resultados}, cierre]
    else:
        nuevos = [cierre]
    grafo.update_state(
        config,
        {"historial": nuevos, "stop_reason": "limite", "respuesta": TEXTO_CORTE},
        as_node="limite",
    )


# -------------------------------------------------------------------
# BLANK 8 — Un mensaje dentro de una conversación
# -------------------------------------------------------------------
# `hablar` procesa UN mensaje del usuario dentro del hilo `thread_id`.
# 8: el `config` de LangGraph: {"configurable": {"thread_id": ...}, "recursion_limit": ...}.
#    Usa el thread_id que recibe la función: el mismo id = la misma conversación con memoria.
def hablar(thread_id: str, mensaje: str, decidir_aprobacion, recursion_limit: int = 25) -> dict:
    """Devuelve el estado final del hilo. `decidir_aprobacion(acciones)` devuelve True/False."""
    config = ___BLANK_8___
    try:
        resultado = grafo.invoke(
            {"mensaje": mensaje, "historial": [{"role": "user", "content": mensaje}]},
            config,
        )
        while "__interrupt__" in resultado:
            acciones = resultado["__interrupt__"][0].value
            resultado = grafo.invoke(Command(resume=decidir_aprobacion(acciones)), config)
        return resultado
    except GraphRecursionError:
        print("  [orquestador] recursion_limit alcanzado; cierro el hilo para poder seguir")
        cerrar_hilo(config)
        return grafo.get_state(config).values


def chat() -> None:
    print("Orquestador de soporte — 'nuevo' otra conversación, 'salir' termina\n")

    def preguntar(acciones: list) -> bool:
        print("\n⏸  Acción pendiente de aprobación:")
        for a in acciones:
            print(f"   - {a['tool']}({a['argumentos']})")
        return input("¿Aprobar? (s/n): ").strip().lower() == "s"

    thread_id = str(uuid.uuid4())
    while True:
        user_input = input("Tú: ").strip()
        if user_input.lower() == "salir":
            print("¡Hasta luego!")
            return
        if user_input.lower() == "nuevo":
            thread_id = str(uuid.uuid4())
            print("\n(nueva conversación)\n")
            continue
        print()
        resultado = hablar(thread_id, user_input, preguntar)
        print(f"\nRuta: {' → '.join(resultado['traza'])}")
        print(f"Agente: {resultado['respuesta']}\n")


if __name__ == "__main__":
    chat()
