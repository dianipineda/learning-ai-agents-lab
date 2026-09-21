"""
Fase 4 — Agente con memoria
============================
Objetivo: construir un agente conversacional que recuerde lo que se dijo
antes, usando el historial de messages como memoria.

La "memoria" de un LLM no es magia — es la lista de mensajes que le pasas.
Cada turno, agregas el nuevo mensaje y pasas la lista completa.
El agente "recuerda" porque ve todo el contexto anterior.

Caso de uso: el asistente de pedidos de Fase 3, ahora conversacional.
El usuario puede hacer varias preguntas seguidas y el agente las conecta.

Ejemplo de conversación:
  Tú: ¿Cómo va mi pedido RP-1001?
  Agente: Tu pedido está en camino, llega en 12 minutos con Carlos M.
  Tú: ¿Y el RP-1002?       ← el agente entiende "el" gracias al historial
  Agente: Ese ya fue entregado.
  Tú: salir
"""

import anthropic
import json
from dotenv import load_dotenv

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)


# -------------------------------------------------------------------
# Función simulada — igual que Fase 3
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


tools = [
    {
        "name": "consultar_estado_pedido",
        "description": "Consulta el estado actual de un pedido dado su número.",
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_pedido": {
                    "type": "string",
                    "description": "El número único del pedido, ej: 'RP-1001'"
                }
            },
            "required": ["numero_pedido"]
        }
    }
]


# -------------------------------------------------------------------
# BLANK 1 — Inicializar el historial de conversación
# -------------------------------------------------------------------
# La memoria de este agente es una lista que va creciendo con cada turno.
# Al principio no hay historial — el agente no sabe nada aún.
#
# Pregunta: ¿qué estructura de datos representa una lista vacía en Python?
# Pista: en Fases 1-3 siempre construiste el array de messages inline.
#        Ahora quieres que esa lista persista entre turnos.

historial = [] #?BLANK_1


print("Agente de soporte Rappi — escribe 'salir' para terminar\n")

# Loop externo: un ciclo por cada turno del usuario
while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir": # o que se parezca a algo como salir
        print("¡Hasta luego!")
        break

    # -------------------------------------------------------------------
    # BLANK 2 — Agregar el mensaje del usuario al historial
    # -------------------------------------------------------------------
    # Antes de llamar a la API necesitas registrar lo que el usuario dijo.
    # La API espera que cada mensaje sea un dict con "role" y "content".
    #
    # Pregunta: ¿qué rol tiene el usuario en el array messages?
    # Pista: en Fase 3 construiste {"role": "user", "content": mensaje_usuario}
    #        Ahora quieres agregar ese dict al historial que ya existe.

    #?___BLANK_2___
    message_user = {"role": "user", "content": user_input}
    historial.append(message_user)

    # Loop interno: maneja el ciclo tool_use completo antes de volver al usuario
    while True:
        respuesta = cliente.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            system="Eres un asistente de soporte de Rappi. Ayudas a los usuarios a conocer el estado de sus pedidos. Sé conciso y amigable.",
            tools=tools,
            # -------------------------------------------------------------------
            # BLANK 3 — Pasar el historial completo a la llamada
            # -------------------------------------------------------------------
            # Aquí está el corazón de la memoria: en vez de construir un array nuevo
            # cada vez, pasas el historial que ha ido creciendo turno a turno.
            #
            # Pregunta: ¿qué variable contiene todos los mensajes anteriores?
            # Pista: es la variable que inicializaste en BLANK 1.

            messages= historial#?___BLANK_3___
        )

        if respuesta.stop_reason == "tool_use":
            # Claude quiere usar una herramienta — ciclo igual que Fase 3,
            # pero ahora dentro del loop y usando el historial compartido.

            # -------------------------------------------------------------------
            # BLANK 4 — Guardar la respuesta intermedia de Claude en el historial
            # -------------------------------------------------------------------
            # Claude respondió con un bloque "tool_use" (quiere llamar a la función).
            # Antes de ejecutar la función, debes guardar esa respuesta en el historial.
            # En la próxima llamada, Claude necesita ver su propio tool_use para
            # saber qué estaba haciendo.
            #
            # Pregunta: ¿qué rol tiene Claude cuando responde? ¿Qué va en "content"?
            # Pista: en Fase 3 lo pasaste como {"role": "assistant", "content": respuesta_1.content}
            #        Ahora haz .append() de ese dict al historial.

            #?___BLANK_4___
            message_claude = {"role": "assistant", "content": respuesta.content}
            historial.append(message_claude)
            print(f"🔥blank 4​------> {respuesta.content}")

            bloque_tool = next(b for b in respuesta.content if b.type == "tool_use")
            resultado = consultar_estado_pedido(bloque_tool.input["numero_pedido"])
            print(f"  [tool] consultar_estado_pedido({bloque_tool.input['numero_pedido']}) → {resultado}")

            # -------------------------------------------------------------------
            # BLANK 5 — Agregar el tool_result al historial y continuar
            # -------------------------------------------------------------------
            # Tienes el resultado de la función. Necesitas dárselo a Claude
            # para que genere su respuesta final.
            # En Fase 3 construiste mensaje_tool_result como dict separado.
            # Ahora haz .append() de ese mismo dict al historial.
            #
            # Estructura que necesitas appendear:
            # {
            #   "role": "user",
            #   "content": [
            #     {
            #       "type": "tool_result",
            #       "tool_use_id": <id del bloque_tool>,
            #       "content": <resultado como string — usa json.dumps()>
            #     }
            #   ]
            # }
            mensaje_tool_result = {
              "role": "user",
              "content": [
                {
                  "type": "tool_result",
                  "tool_use_id": bloque_tool.id,
                  "content": json.dumps(resultado)
                }
              ]
            }
            #?___BLANK_5___
            historial.append(mensaje_tool_result)
            print(f"🔥blank 5​------> {respuesta.content}")

            # El loop interno continúa → Claude verá el tool_result y responderá

        else:
            # Claude respondió con texto final — turno completado

            # -------------------------------------------------------------------
            # BLANK 6 — Guardar la respuesta final de Claude en el historial
            # -------------------------------------------------------------------
            # ¡Este es el paso más importante de toda la fase!
            # Si no guardas la respuesta aquí, en el siguiente turno Claude
            # no sabrá qué dijo antes — el agente "olvidará" la conversación.
            #
            # Pregunta: ¿es el mismo patrón que BLANK 4?
            # Pista: sí, casi idéntico — mismo rol, mismo campo content.

            #?___BLANK_6___
            message_claude_with_tool = {"role": "assistant", "content": respuesta.content}
            historial.append(message_claude_with_tool)
            print(f"🔥blank 5------> {respuesta.content}")
            print(f"\nAgente: {respuesta.content[0].text}\n")
            break  # Turno completado → volver al loop externo para el próximo input
