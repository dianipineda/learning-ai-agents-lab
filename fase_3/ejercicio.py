"""
Fase 3 — Tool Calling
=====================
Objetivo: entender el ciclo completo de tool calling con la API de Anthropic.

El ciclo tiene 4 pasos:
  1. Tú defines tools y se las ofreces a Claude
  2. Claude decide llamar una tool (stop_reason = "tool_use")
  3. Tú ejecutas la función real y devuelves el resultado
  4. Claude genera la respuesta final usando ese resultado

Caso de uso: agente que consulta el estado de un pedido de Rappi.
"""

import anthropic
import json
from dotenv import load_dotenv

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

# -------------------------------------------------------------------
# Función simulada — en producción esto consultaría una base de datos
# -------------------------------------------------------------------
def consultar_estado_pedido(numero_pedido: str) -> dict:
    pedidos_simulados = {
        "RP-1001": {"estado": "en_camino", "tiempo_restante_min": 12, "repartidor": "Carlos M."},
        "RP-1002": {"estado": "entregado", "tiempo_restante_min": 0, "repartidor": "Ana G."},
        "RP-1003": {"estado": "preparando", "tiempo_restante_min": 25, "repartidor": None},
    }
    return pedidos_simulados.get(
        numero_pedido,
        {"estado": "no_encontrado", "tiempo_restante_min": None, "repartidor": None}
    )


# -------------------------------------------------------------------
# BLANK 1 — Definir el schema de la tool
# -------------------------------------------------------------------
# Una tool tiene 3 campos obligatorios:
#   "name"         → identificador único (string, snake_case)
#   "description"  → para qué sirve (Claude la lee para decidir cuándo usarla)
#   "input_schema" → JSON Schema de los parámetros que acepta la función
#
# El "input_schema" sigue el estándar JSON Schema:
#   "type": "object"
#   "properties": { "param": { "type": "...", "description": "..." } }
#   "required": ["param"]
#
# Pista: la función real recibe un solo argumento: numero_pedido (string)
#
# ¿Qué iría en el dict de tools?

tools = [
    ___BLANK_1___
]


# -------------------------------------------------------------------
# Pregunta del usuario
# -------------------------------------------------------------------
mensaje_usuario = "Hola, ¿me puedes decir cómo va mi pedido RP-1001?"

print(f"Usuario: {mensaje_usuario}\n")


# -------------------------------------------------------------------
# BLANK 2 — Primera llamada: ofrecer las tools a Claude
# -------------------------------------------------------------------
# Además de model, max_tokens y messages, hay un parámetro nuevo: tools=
# Le pasa la lista de tools disponibles para que Claude decida si usar alguna.
#
# Pista: es igual a las llamadas anteriores + un argumento extra

respuesta_1 = cliente.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": mensaje_usuario}],
    ___BLANK_2___
)

print(f"stop_reason: {respuesta_1.stop_reason}")
print(f"content blocks: {[b.type for b in respuesta_1.content]}\n")


# -------------------------------------------------------------------
# BLANK 3 — Detectar que Claude quiere usar una tool
# -------------------------------------------------------------------
# Cuando Claude quiere llamar una tool, stop_reason es "tool_use"
# y en respuesta_1.content hay un bloque de tipo "tool_use" con:
#   .name   → nombre de la tool que quiere llamar
#   .input  → dict con los argumentos
#   .id     → identificador único de esta llamada (lo necesitas para el resultado)
#
# Pista: itera respuesta_1.content buscando el bloque con type == "tool_use"

if respuesta_1.stop_reason == "tool_use":

    bloque_tool = ___BLANK_3___

    print(f"Claude quiere llamar: {bloque_tool.name}")
    print(f"Con argumentos: {bloque_tool.input}\n")

    # ---------------------------------------------------------------
    # BLANK 4 — Ejecutar la función real y construir el tool_result
    # ---------------------------------------------------------------
    # Ahora ejecutas la función Python real con los argumentos que Claude eligió.
    # Luego debes devolvérselo en un mensaje especial con role "user" que contiene
    # un bloque de tipo "tool_result":
    #
    # {
    #   "role": "user",
    #   "content": [
    #     {
    #       "type": "tool_result",
    #       "tool_use_id": <el id del bloque_tool>,
    #       "content": <resultado como string>
    #     }
    #   ]
    # }
    #
    # Pista 1: ejecuta consultar_estado_pedido() con el argumento correcto de bloque_tool.input
    # Pista 2: el content del tool_result debe ser un string → usa json.dumps()

    resultado_funcion = consultar_estado_pedido(___BLANK_4a___)

    mensaje_tool_result = ___BLANK_4b___

    print(f"Resultado de la función: {resultado_funcion}\n")

    # ---------------------------------------------------------------
    # BLANK 5 — Segunda llamada: Claude genera la respuesta final
    # ---------------------------------------------------------------
    # Claude necesita ver toda la conversación para responder:
    #   1. El mensaje original del usuario
    #   2. Su propia respuesta con el bloque tool_use (respuesta_1.content)
    #   3. El tool_result que acabas de construir
    #
    # Pista: el array messages tiene 3 elementos en este orden

    respuesta_final = cliente.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        tools=tools,
        messages=___BLANK_5___
    )

    print(f"Claude: {respuesta_final.content[0].text}")

else:
    # Claude respondió directo sin usar tools
    print(f"Claude (sin tool): {respuesta_1.content[0].text}")
