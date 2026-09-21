"""
Fase 9 — Ejercicio 3: Ensayo general (supervisor + aprobación humana + evaluación)
=================================================================================
Objetivo: juntar las tres piezas del curso antes del orquestador final:
  1. EQUIPO: supervisor + especialistas con traspasos (ejercicio 2, ya resuelto aquí).
  2. HUMANO EN EL BUCLE: `crear_reclamo` (efecto real) pide aprobación con `interrupt`
     (fase 8, ejercicio 1). La aprobación aplica a cualquier agente que la llame.
  3. EVALUACIÓN: un eval que corre casos de punta a punta sobre el grafo completo y verifica
     tres cosas por caso: la RUTA (qué agente atendió primero), las TOOLS que se intentaron
     usar, y los EFECTOS reales (cuántos reclamos se crearon). Aprueba o rechaza automáticamente
     los reclamos según el caso, para probar también el camino del "no".

Dos modos:
    python ejercicios/fase_9/ejercicio_3.py           → corre el eval (código de salida 0/1)
    python ejercicios/fase_9/ejercicio_3.py --chat    → conversas tú y apruebas a mano

Los guardrails de la fase 8 (presupuesto de tokens, validación de argumentos, reintentos) no
se repiten aquí para centrarnos en la arquitectura; los integrarás todos en la Fase 10 (proyecto final).
"""

import operator
import sys
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

# Tools con efectos reales: requieren aprobación humana antes de ejecutarse.
SENSIBLES = {"crear_reclamo"}

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
    agente: str
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str
    traza: Annotated[list, operator.add]
    traspasos: Annotated[int, operator.add]
    aprobado: bool


def supervisor(estado: Estado) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=SYSTEM_SUPERVISOR,
        tools=[ELEGIR_AGENTE],
        tool_choice={"type": "tool", "name": "elegir_agente"},
        messages=[{"role": "user", "content": estado["mensaje"]}],
    )
    agente = next(b for b in respuesta.content if b.type == "tool_use").input["agente"]
    print(f"  [supervisor] → {agente}")
    return {"agente": agente, "traza": [agente]}


def especialista(estado: Estado) -> dict:
    nombre = estado["agente"]
    herramientas = [t for t in TOOLS if t["name"] in AGENTES[nombre]["tools"]] + [TRANSFERIR]
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=1024,
        system=AGENTES[nombre]["system"],
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


# -------------------------------------------------------------------
# BLANK 1 — Pedir aprobación
# -------------------------------------------------------------------
# `interrupt(valor)` pausa el grafo y devuelve la decisión humana al reanudar con Command(resume=...).
# 1: guarda en `aprobado` lo que devuelva interrupt(...) al pasarle la lista `acciones`.
#
# Recuerda: al reanudar, este nodo se ejecuta DESDE EL INICIO. Por eso aquí no hay efectos
# antes del interrupt (no se llama a la API ni se crea nada).
def aprobar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    acciones = [
        {"tool": b["name"], "argumentos": b["input"]}
        for b in ultimo["content"]
        if b["type"] == "tool_use" and b["name"] in SENSIBLES
    ]
    aprobado = interrupt(acciones)
    return {"aprobado": aprobado}


def tools_node(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    aprobado = estado.get("aprobado", False)  # fail closed: sin decisión explícita, no se ejecuta
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


def traspasar(estado: Estado) -> dict:
    ultimo = estado["historial"][-1]
    pedido = next(b for b in ultimo["content"] if b["type"] == "tool_use" and b["name"] == "transferir_a")
    destino = pedido["input"]["agente"]
    motivo = pedido["input"].get("motivo", "")
    if estado.get("traspasos", 0) >= MAX_TRASPASOS or destino == estado["agente"]:
        print(f"  [traspaso] a {destino} RECHAZADO")
        texto = "Traspaso rechazado. Resuelve tú con tus herramientas o explícale al usuario lo que no puedes hacer."
        return {"historial": [{"role": "user", "content": responder_llamadas(ultimo, pedido["id"], texto, True)}]}
    print(f"  [traspaso] {estado['agente']} → {destino} (motivo: {motivo})")
    texto = f"Traspaso a '{destino}' realizado. Motivo: {motivo}. Continúa tú atendiendo al usuario."
    return {
        "historial": [{"role": "user", "content": responder_llamadas(ultimo, pedido["id"], texto, False)}],
        "agente": destino,
        "traza": [destino],
        "traspasos": 1,
    }


# -------------------------------------------------------------------
# BLANK 2 — Enrutar: traspaso, aprobación, herramientas o fin
# -------------------------------------------------------------------
# El traspaso ya tiene prioridad. 2: la condición para ir a "aprobar": algún bloque del último
# mensaje es un tool_use cuyo nombre está en SENSIBLES.
def decidir(estado: Estado) -> str:
    if estado["stop_reason"] != "tool_use":
        return END
    ultimo = estado["historial"][-1]
    if any(b["type"] == "tool_use" and b["name"] == "transferir_a" for b in ultimo["content"]):
        return "traspasar"
    if any(b["type"] == "tool_use" and b["name"] in SENSIBLES for b in ultimo["content"]):
        return "aprobar"
    return "tools"


# -------------------------------------------------------------------
# BLANK 3 — El grafo completo
# -------------------------------------------------------------------
# 3a: mapa de rutas de `decidir` (ahora hay un destino más): traspasar, aprobar, tools y END.
# 3b: la arista que lleva de "aprobar" a "tools" (tras decidir el humano, se ejecuta o se rechaza).
builder = StateGraph(Estado)
builder.add_node("supervisor", supervisor)
builder.add_node("especialista", especialista)
builder.add_node("aprobar", aprobar)
builder.add_node("tools", tools_node)
builder.add_node("traspasar", traspasar)

builder.add_edge(START, "supervisor")
builder.add_edge("supervisor", "especialista")
builder.add_conditional_edges(
    "especialista",
    decidir,
    {"traspasar": "traspasar", "aprobar": "aprobar", "tools": "tools", END: END},
)
builder.add_edge("aprobar", "tools")
builder.add_edge("tools", "especialista")
builder.add_edge("traspasar", "especialista")

# `interrupt` exige checkpointer: guarda el estado del grafo mientras espera al humano.
grafo = builder.compile(checkpointer=MemorySaver())


def correr(mensaje: str, decidir_aprobacion) -> dict:
    """Corre UNA conversación nueva (hilo nuevo). `decidir_aprobacion(acciones)` devuelve True/False."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 25}
    resultado = grafo.invoke(
        {"mensaje": mensaje, "historial": [{"role": "user", "content": mensaje}]},
        config,
    )
    while "__interrupt__" in resultado:
        acciones = resultado["__interrupt__"][0].value
        resultado = grafo.invoke(Command(resume=decidir_aprobacion(acciones)), config)
    return resultado


# ===================================================================
# EVALUACIÓN de punta a punta
# ===================================================================
# Cada caso dice qué esperamos:
#   agente   → primer agente elegido por el supervisor
#   tools    → conjunto de tools que el agente INTENTÓ usar (aunque el humano las rechace)
#   reclamos → cuántos reclamos deben haberse CREADO de verdad (efectos reales)
#   aprobar  → qué decide el "humano automático" cuando se le pide aprobación
EVALS = [
    {"nombre": "consulta de pedido", "mensaje": "¿Cómo va mi pedido RP-1001?",
     "agente": "pedidos", "tools": {"consultar_estado_pedido"}, "reclamos": 0},
    {"nombre": "consulta de pago", "mensaje": "¿Ya me cobraron el pedido RP-1002?",
     "agente": "pagos", "tools": {"consultar_pago"}, "reclamos": 0},
    {"nombre": "queja aprobada", "mensaje": "Mi pedido RP-1002 llegó frío y quiero registrar un reclamo",
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 1, "aprobar": True},
    {"nombre": "queja rechazada", "mensaje": "Mi pedido RP-1003 llegó incompleto y quiero registrar un reclamo",
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 0, "aprobar": False},
    {"nombre": "reclamo sin número de pedido", "mensaje": "Quiero registrar un reclamo",
     "agente": "reclamos", "tools": set(), "reclamos": 0},
]
UMBRAL = 0.8  # fracción mínima de casos que deben pasar


def evaluar_caso(caso: dict) -> dict:
    RECLAMOS.clear()  # cada caso parte sin reclamos previos
    resultado = correr(caso["mensaje"], lambda acciones: caso.get("aprobar", True))

    # -------------------------------------------------------------------
    # BLANK 4 — ¿Qué tools intentó usar el agente?
    # -------------------------------------------------------------------
    # 4: un conjunto (set) con los `name` de todos los bloques tool_use de los mensajes con
    #    role "assistant" en resultado["historial"], SIN contar "transferir_a" (es coordinación,
    #    no una acción de negocio).
    #    Ojo: el primer mensaje del historial (user) trae `content` como string, no como lista.
    tools_usadas = {
        b["name"]
        for m in resultado["historial"]
        if m["role"] == "assistant"
        for b in m["content"]
        if b["type"] == "tool_use" and b["name"] != "transferir_a"
    }

    # BLANK 5, 6, 7 — Las tres verificaciones (cada una es un booleano)
    #   5: la ruta: el PRIMER agente de resultado["traza"] es el esperado (caso["agente"]).
    #   6: las tools intentadas coinciden exactamente con caso["tools"].
    #   7: los efectos: la cantidad de reclamos creados (len(RECLAMOS)) es caso["reclamos"].
    #
    # Pregunta para razonar: ¿por qué verificar EFECTOS (RECLAMOS) y no solo lo que el agente dice?
    ok_ruta = resultado["traza"][0] == caso["agente"]
    ok_tools = tools_usadas == caso["tools"]
    ok_efectos = len(RECLAMOS) == caso["reclamos"]
    return {"ok": ok_ruta and ok_tools and ok_efectos,
            "detalle": {"ruta": ok_ruta, "tools": ok_tools, "efectos": ok_efectos},
            "traza": resultado["traza"], "tools_usadas": tools_usadas}


def correr_eval() -> int:
    aciertos = 0
    for caso in EVALS:
        print(f"\n▶ {caso['nombre']}: {caso['mensaje']!r}")
        r = evaluar_caso(caso)
        aciertos += r["ok"]
        marca = "✓" if r["ok"] else "✗"
        print(f"  {marca} {r['detalle']}  ruta={' → '.join(r['traza'])}  tools={sorted(r['tools_usadas'])}")

    # ---------------------------------------------------------------
    # BLANK 8 — Puerta de calidad
    # ---------------------------------------------------------------
    # 8: `exito` es True si la fracción de casos pasados (aciertos / total) alcanza UMBRAL.
    exito = aciertos / len(EVALS) >= UMBRAL
    print(f"\nResultado: {aciertos}/{len(EVALS)} casos · umbral {UMBRAL:.0%} → {'APROBADO' if exito else 'RECHAZADO'}")
    return 0 if exito else 1


def chat() -> None:
    print("Equipo de soporte con aprobación humana — 'salir' termina\n")

    def preguntar(acciones: list) -> bool:
        print("\n⏸  Acción pendiente de aprobación:")
        for a in acciones:
            print(f"   - {a['tool']}({a['argumentos']})")
        return input("¿Aprobar? (s/n): ").strip().lower() == "s"

    while True:
        user_input = input("Tú: ").strip()
        if user_input.lower() == "salir":
            print("¡Hasta luego!")
            return
        print()
        try:
            resultado = correr(user_input, preguntar)
            print(f"\nRuta: {' → '.join(resultado['traza'])}")
            print(f"Agente: {resultado['respuesta']}\n")
        except GraphRecursionError:
            print("\nAgente: Lo siento, no pude completar tu solicitud. Un agente humano te contactará.\n")


if "--chat" in sys.argv:
    chat()
else:
    sys.exit(correr_eval())
