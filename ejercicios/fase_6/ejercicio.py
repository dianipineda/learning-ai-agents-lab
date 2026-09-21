"""
Fase 6 — Agente de Soporte de Pedidos (sistema completo)
=========================================================
Objetivo: integrar TODO lo aprendido en un solo sistema.

  Fase 2 → salida estructurada (JSON del clasificador)
  Fase 3 → tool calling (varias tools)
  Fase 4 → memoria (historial que crece turno a turno)
  Fase 5 → orquestador (clasificador + ejecutor)

Arquitectura:
  Usuario
    ↓ mensaje
  Orquestador
    ↓
  Clasificador (sin memoria) → { "tipo", "numero_pedido" }
    ↓
  Ejecutor (CON memoria + tools) → loop interno while tool_use → respuesta final

Novedades respecto a fases anteriores:
  - Dos tools: consultar_estado_pedido y crear_reclamo
  - Un despachador de tools (dict nombre → función) en vez de un if por tool
  - Loop interno con límite de iteraciones (guardrail contra ciclos infinitos)
  - Claude puede pedir VARIAS tools en un mismo turno: hay que responder todas
"""

import anthropic
import json
from dotenv import load_dotenv

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

MODELO = "claude-sonnet-5"
MAX_ITERACIONES = 5


# -------------------------------------------------------------------
# Funciones simuladas
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
    # En producción esto escribiría en una base de datos / CRM
    return {"reclamo_id": f"REC-{numero_pedido[-4:]}", "estado": "abierto", "motivo": motivo}


# -------------------------------------------------------------------
# BLANK 1 — Schema de la segunda tool (crear_reclamo)
# -------------------------------------------------------------------
# consultar_estado_pedido ya está definida. Define crear_reclamo con:
#   - name: "crear_reclamo"
#   - description: cuándo debe usarla Claude (el usuario reporta un problema
#     con un pedido y quiere que se registre un reclamo)
#   - input_schema: objeto con DOS propiedades string requeridas:
#       "numero_pedido" y "motivo"
#
# Pista: es el mismo patrón de la Fase 3, pero con dos parámetros en "required".
tools = [
    {
        "name": "consultar_estado_pedido",
        "description": "Consulta el estado actual de un pedido dado su número.",
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_pedido": {"type": "string", "description": "Ej: 'RP-1001'"}
            },
            "required": ["numero_pedido"],
        },
    },
    ___BLANK_1___
]

# -------------------------------------------------------------------
# BLANK 2 — Despachador de tools
# -------------------------------------------------------------------
# En vez de un if/elif por cada tool, usa un diccionario que mapee el
# nombre de la tool (string) a la función Python que la implementa.
#
# Pista: { "consultar_estado_pedido": consultar_estado_pedido, ... }
#        Luego se llama así: FUNCIONES[nombre](**argumentos)
FUNCIONES = ___BLANK_2___


# ===================================================================
# AGENTE 1 — CLASIFICADOR (sin memoria)
# ===================================================================
SYSTEM_CLASIFICADOR = """
Eres un clasificador de solicitudes de soporte de pedidos. Devuelve ÚNICAMENTE JSON:
{ "tipo": "consulta_pedido" | "queja" | "saludo" | "otro", "numero_pedido": "<número o null>" }
Sin texto extra ni bloques Markdown.
"""


def clasificar_mensaje(mensaje_usuario: str) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=SYSTEM_CLASIFICADOR,
        messages=[{"role": "user", "content": mensaje_usuario}],
    )
    texto = next(b.text for b in respuesta.content if b.type == "text").strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    clasificacion = json.loads(texto)
    print(f"  [clasificador] → {clasificacion}")
    return clasificacion


# ===================================================================
# AGENTE 2 — EJECUTOR (con memoria + tools)
# ===================================================================
# -------------------------------------------------------------------
# BLANK 3 — System prompt del Ejecutor con el resultado del Clasificador
# -------------------------------------------------------------------
# Escribe una función que reciba `clasificacion` (dict) y devuelva un
# system prompt. Debe:
#   a) Definir el rol: agente de soporte de pedidos de Rappi
#   b) Incluir el tipo y el número de pedido detectados por el clasificador
#      (usa un f-string) para que el ejecutor los tenga como contexto
#   c) Dar reglas: si es queja y hay número de pedido, primero consultar el
#      estado y luego crear el reclamo; nunca inventar datos; si falta el
#      número de pedido, pedírselo al usuario
#
# Pista: en la Fase 5 el prompt cambiaba con if/elif; aquí puedes usar UN prompt
# con f-string, porque el ejecutor ahora tiene todas las tools disponibles.
def construir_system_ejecutor(clasificacion: dict) -> str:
    tipo = clasificacion.get("tipo", "otro")
    numero_pedido = clasificacion.get("numero_pedido")

    return ___BLANK_3___


def ejecutar_respuesta(historial: list, clasificacion: dict) -> str:
    """
    Corre el loop interno del ejecutor sobre `historial` (que ya incluye el
    último mensaje del usuario) y devuelve el texto final.
    """
    system_ejecutor = construir_system_ejecutor(clasificacion)

    for _ in range(MAX_ITERACIONES):
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=1024,
            system=system_ejecutor,
            tools=tools,
            messages=historial,
        )

        # ---------------------------------------------------------------
        # BLANK 4 — Condición de salida del loop
        # ---------------------------------------------------------------
        # Si Claude NO pidió ninguna tool, terminó: guarda su respuesta en el
        # historial (memoria, Fase 4) y devuelve el texto.
        #
        # Pista: stop_reason != "tool_use". Recuerda que para el historial
        # se guarda respuesta.content (completo) y para el usuario solo el texto.
        ___BLANK_4___

        # ---------------------------------------------------------------
        # BLANK 5 — Ejecutar TODAS las tools pedidas y devolver resultados
        # ---------------------------------------------------------------
        # Claude puede pedir varias tools en el mismo turno (varios bloques
        # tool_use). Debes:
        #   1. Guardar respuesta.content en el historial (role assistant)
        #   2. Recorrer TODOS los bloques con type == "tool_use"
        #   3. Ejecutar FUNCIONES[bloque.name](**bloque.input)
        #   4. Construir un tool_result por bloque (tool_use_id = bloque.id,
        #      content = json.dumps(resultado))
        #   5. Guardar UN solo mensaje role user con la lista de tool_results
        #
        # Pista: todos los tool_result van juntos en el content de UN mensaje.
        ___BLANK_5___

    return "Lo siento, no pude completar tu solicitud. Un agente humano te contactará."


# ===================================================================
# ORQUESTADOR — memoria + clasificador + ejecutor
# ===================================================================
# -------------------------------------------------------------------
# BLANK 6 — Memoria entre turnos
# -------------------------------------------------------------------
# Inicializa el historial UNA vez, fuera del while, y dentro del loop
# agrega el mensaje del usuario antes de llamar al ejecutor.
#
# Pista: mismo patrón de la Fase 4. ¿Dónde va la inicialización para que
# no se borre en cada turno?
historial = ___BLANK_6a___

print("Agente de soporte Rappi (sistema completo) — escribe 'salir' para terminar\n")

while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir":
        print("¡Hasta luego!")
        break

    print()
    ___BLANK_6b___

    clasificacion = clasificar_mensaje(user_input)
    respuesta_final = ejecutar_respuesta(historial, clasificacion)

    print(f"\nAgente: {respuesta_final}\n")
