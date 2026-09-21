"""
Fase 5 — Orquestador con 2 agentes
====================================
Objetivo: coordinar dos agentes especializados en lugar de uno que haga todo.

Arquitectura:
  Usuario
    ↓ mensaje
  Orquestador (este código)
    ↓ llama
  Agente Clasificador (Claude #1) → devuelve JSON: { "tipo": "...", "numero_pedido": "..." }
    ↓ resultado estructurado
  Agente Ejecutor (Claude #2, con tools si aplica) → respuesta final al usuario

Tipos de solicitud que maneja el Clasificador:
  - "consulta_pedido"  → el usuario quiere saber el estado de un pedido
  - "queja"           → el usuario está molesto / reporta un problema
  - "saludo"          → el usuario saluda o hace pregunta general
  - "otro"            → no encaja en ninguna categoría anterior

Por qué dos agentes:
  - Separación de responsabilidades: cada uno hace una sola cosa bien
  - El Clasificador puede ser un modelo barato (en producción sería Haiku)
  - El Ejecutor tiene su system prompt optimizado para responder, no para clasificar
  - Se pueden mejorar y mantener de forma independiente
"""

import anthropic
import json
from dotenv import load_dotenv

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)


# -------------------------------------------------------------------
# Función simulada — igual que fases anteriores
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


tools_ejecutor = [
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


# ===================================================================
# AGENTE 1 — CLASIFICADOR
# ===================================================================
def clasificar_mensaje(mensaje_usuario: str) -> dict:
    """
    Llama a Claude con un system prompt de clasificación.
    Devuelve un dict con al menos: { "tipo": "...", "numero_pedido": "..." }
    """

    # -------------------------------------------------------------------
    # BLANK 1 — System prompt del Clasificador
    # -------------------------------------------------------------------
    # Este agente tiene UN solo trabajo: leer el mensaje y devolver JSON.
    # El system prompt debe:
    #   a) Decirle a Claude que es un clasificador (no un asistente de soporte)
    #   b) Definir los 4 tipos posibles: consulta_pedido, queja, saludo, otro
    #   c) Especificar el formato JSON exacto que debe devolver:
    #      { "tipo": "<tipo>", "numero_pedido": "<número o null>" }
    #   d) Ser estricto: solo JSON, sin texto extra, sin explicaciones
    #
    # Pista: en Fase 2 aprendiste a forzar output estructurado con JSON Schema
    # en el prompt. Aplica ese mismo patrón aquí.

    system_clasificador = """___BLANK_1___"""

    # -------------------------------------------------------------------
    # BLANK 2 — Llamada al Clasificador
    # -------------------------------------------------------------------
    # Llama a claude con:
    #   - model: "claude-sonnet-5" (en prod usarías haiku para este agente)
    #   - max_tokens: 256 (la clasificación es corta)
    #   - el system prompt del BLANK 1
    #   - messages: solo el mensaje del usuario, sin historial
    #
    # Pista: es la llamada más simple de todas las fases — sin tools, sin historial

    respuesta_clasificador = ___BLANK_2___

    texto = respuesta_clasificador.content[0].text.strip()

    # Igual que Fase 2: Claude a veces envuelve en ```json ... ```
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1]
        texto = texto.rsplit("```", 1)[0]

    clasificacion = json.loads(texto)
    print(f"  [clasificador] → {clasificacion}")
    return clasificacion


# ===================================================================
# AGENTE 2 — EJECUTOR
# ===================================================================
def ejecutar_respuesta(mensaje_usuario: str, clasificacion: dict) -> str:
    """
    Llama a Claude con el contexto de la clasificación.
    Maneja el ciclo tool_use si el tipo es consulta_pedido.
    Devuelve el texto final de respuesta al usuario.
    """

    # -------------------------------------------------------------------
    # BLANK 3 — System prompt del Ejecutor (condicional a la clasificación)
    # -------------------------------------------------------------------
    # A diferencia del Clasificador, este agente SÍ habla con el usuario.
    # Su system prompt debe cambiar según el tipo clasificado:
    #
    #   - "consulta_pedido" → asistente de soporte que puede consultar pedidos
    #   - "queja"           → agente empático, prioriza disculpa y solución
    #   - "saludo"          → asistente amigable, responde directo sin buscar pedidos
    #   - "otro"            → asistente general, reconoce que no puede ayudar con eso
    #
    # Pista: usa un if/elif/else para construir el string system_ejecutor
    # según clasificacion["tipo"]. No necesitas ser muy largo — 1-2 oraciones por caso.

    tipo = clasificacion.get("tipo", "otro")

    if tipo == "consulta_pedido":
        system_ejecutor = """___BLANK_3a___"""
    elif tipo == "queja":
        system_ejecutor = """___BLANK_3b___"""
    elif tipo == "saludo":
        system_ejecutor = """___BLANK_3c___"""
    else:
        system_ejecutor = """___BLANK_3d___"""

    # -------------------------------------------------------------------
    # BLANK 4 — Llamada al Ejecutor con tools (solo si es consulta_pedido)
    # -------------------------------------------------------------------
    # El Ejecutor necesita tools SOLO cuando el tipo es "consulta_pedido".
    # Para los demás tipos, no tiene sentido ofrecerle la tool — Claude
    # no la va a usar y solo encarece la llamada.
    #
    # Completa la llamada pasando tools=tools_ejecutor solo si corresponde.
    # Para el parámetro tools, usa un if inline (ternario) o un if antes de la llamada.
    #
    # Pista: tools_ejecutor si tipo == "consulta_pedido", si no: no pases tools
    # (o pasa tools=[] — la API acepta lista vacía)

    respuesta = cliente.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system_ejecutor,
        messages=[{"role": "user", "content": mensaje_usuario}],
        tools=___BLANK_4___
    )

    # -------------------------------------------------------------------
    # BLANK 5 — Ciclo tool_use del Ejecutor
    # -------------------------------------------------------------------
    # Si el tipo es "consulta_pedido", Claude puede querer usar la tool.
    # El ciclo es idéntico al de Fase 3:
    #   1. Detectar stop_reason == "tool_use"
    #   2. Extraer el bloque tool_use
    #   3. Ejecutar la función real
    #   4. Construir el tool_result y hacer la segunda llamada con historial de 3 mensajes
    #   5. Devolver el texto final
    #
    # Si no es "consulta_pedido", Claude responde directo — solo devuelve el texto.
    #
    # Pista: es casi idéntico al if/else de Fase 3. La diferencia: aquí está
    # dentro de una función que debe *retornar* el texto final.

    ___BLANK_5___


# ===================================================================
# ORQUESTADOR — coordina los dos agentes
# ===================================================================
print("Agente de soporte Rappi (orquestador) — escribe 'salir' para terminar\n")

while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir":
        print("¡Hasta luego!")
        break

    print()

    # Paso 1: Clasificar
    clasificacion = clasificar_mensaje(user_input)

    # Paso 2: Ejecutar según clasificación
    respuesta_final = ejecutar_respuesta(user_input, clasificacion)

    print(f"\nAgente: {respuesta_final}\n")
