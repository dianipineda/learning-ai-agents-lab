# =============================================================================
# FASE 2 — Prompt Engineering + Structured Output
# Objetivo: darle instrucciones precisas a Claude y recibir JSON, no texto libre
# =============================================================================
#
# INSTRUCCIONES:
#   Hay 4 blancos marcados con ___BLANK_X___
#   Completa los blancos, luego corre: python fase_2/ejercicio.py
#
# Contexto del caso:
#   Estamos construyendo un agente de soporte de pedidos.
#   Llega un mensaje de un cliente y necesitamos extraer datos estructurados
#   para que el sistema sepa qué hacer con ese caso automáticamente.
#
# =============================================================================

import os
import json
from dotenv import load_dotenv
import anthropic

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": os.getenv("ANTHROPIC_WORKSPACE_ID", "")}
)


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 1 — El System Prompt
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: el system prompt es un mensaje especial que le dice al modelo
# CÓMO debe comportarse ANTES de que el usuario hable.
# No lo ve el usuario — es tu contrato privado con el modelo.
# Es la herramienta más poderosa del prompt engineering.
#
# Pista: queremos que Claude actúe como un clasificador de tickets de soporte
#        y que SIEMPRE responda con un JSON válido (sin texto adicional).
#        Un buen system prompt es específico, da ejemplos del formato esperado,
#        y anticipa los casos borde.
#
# Completa el system prompt (es texto libre — escríbelo tú):
SYSTEM_PROMPT = """
    Eres un clasificador experto de tickets de soporte técnico para pedidos. Tu tarea es analizar el asunto y el cuerpo del ticket recibido y extraer la información estructurada respetando estrictamente el formato JSON definido.

    ### Reglas de Extracción y Clasificación

    1. **numero_pedido** (integer | null): 
    - Busca el número de pedido en el cuerpo del ticket. Si no aparece, búscalo en el asunto.
    - Si no existe en ningún lugar, asigna `null`.

    2. **ts_recepcion_ticket** (string): 
    - Cadena con la fecha y hora de recepción del ticket en formato "YYYY-MM-DD HH:MM:SS".

    3. **estado_percibido_pedido** (string): 
    - Selecciona exactamente uno de los siguientes 3 valores:
        * `"sin llegar"`: El pedido no ha sido entregado.
        * `"recibido con errores de calidad percibida"`: El pedido llegó pero tiene fallas, faltantes o averías.
        * `"recibido"`: El pedido llegó completo y en buen estado.

    4. **pedido_destinado_a** (string | null): 
    - Infiere del texto la finalidad o uso que el usuario le dará al pedido (ej. "regalo de cumpleaños"). Si no se menciona implícita ni explícitamente, asigna `null`.

    5. **satisfaccion_usuario_ticket** (string): 
    - Infiere la emoción/tono del usuario a partir del texto.
    - Valores permitidos: `"muy contento"`, `"contento"`, `"neutral"`, `"molesto"`, `"muy molesto"`.

    6. **pregunta_usuario** (string | null): 
    - Resume brevemente la pregunta o solicitud de información implícita/explícita (ej. rastreo, compensación, estado). 
    - Si el ticket es únicamente un reporte o queja sin preguntas ni solicitudes de información, asigna `null`.

    7. **sentido_de_urgencia** (string): 
    - `"alto"`: Si el texto indica prisa, fechas límite cercanas ("mañana", "hoy") o alta frustración.
    - `"bajo"`: Si es un ticket de felicitación/agradecimiento (`satisfaccion_usuario_ticket` es "contento" o "muy contento" y `estado_percibido_pedido` es "recibido").
    - `"medio"`: Si no hay urgencia explícita ni aplica la condición de urgencia baja.

    8. **queja_calidad** (string | null): 
    - Si `estado_percibido_pedido` es `"recibido con errores de calidad percibida"`, resume brevemente la falla expresada.
    - Si el estado es `"sin llegar"` o `"recibido"`, asigna estrictamente `null`.

    ### Formato de Salida
    Responde ÚNICAMENTE con el objeto JSON estructurado, sin texto explicativo adicional ni bloques Markdown fuera del JSON.

    Esquema JSON esperado:
    {
    "numero_pedido": int | null,
    "ts_recepcion_ticket": "YYYY-MM-DD HH:MM:SS",
    "estado_percibido_pedido": "sin llegar" | "recibido con errores de calidad percibida" | "recibido",
    "pedido_destinado_a": string | null,
    "satisfaccion_usuario_ticket": "muy contento" | "contento" | "neutral" | "molesto" | "muy molesto",
    "pregunta_usuario": string | null,
    "sentido_de_urgencia": "alto" | "medio" | "bajo",
    "queja_calidad": string | null
    }
"""


# El mensaje del cliente que vamos a analizar
mensaje_cliente = """
Hola, mi pedido #45231 no llegó. Ya pasaron 3 días del tiempo estimado
y cuando lo rastro dice 'en tránsito' desde hace 2 días. Necesito saber
qué pasó porque es un regalo de cumpleaños para mañana. Estoy muy molesto.
"""


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 2 — Agregar el system prompt a la llamada
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: la API de Anthropic acepta un parámetro separado llamado "system"
# (no va dentro del array messages). Es el lugar oficial para el system prompt.
#
# Pista: en la Fase 1 tu llamada tenía: model=, max_tokens=, messages=
#        Ahora necesitas agregar un cuarto parámetro llamado igual que el concepto.
#
# Completa el parámetro que falta:
respuesta = cliente.messages.create(
    model="claude-sonnet-5",
    max_tokens=512,
    system=SYSTEM_PROMPT,
    messages=[
        {"role": "user", "content": mensaje_cliente}
    ]
)


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 3 — Parsear el JSON
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: Claude responde con texto (string). Aunque ese texto sea JSON válido,
# Python no lo trata como diccionario hasta que lo conviertes explícitamente.
# Para eso existe el módulo "json" que ya importamos arriba.
#
# Pista: hay una función en el módulo json que convierte un string JSON
#        a un diccionario Python. Se llama... (piensa: lo opuesto de json.dumps)
#
# Completa:
texto_respuesta = respuesta.content[0].text
texto_limpio = texto_respuesta.strip()
if texto_limpio.startswith("```"):
    texto_limpio = texto_limpio.split("\n",1)[1]
    texto_limpio = texto_limpio.rsplit("```",1)[0]
print("DEGUG: ",repr(texto_respuesta)) #repr es para ver la radiografia del texto, tal como lo procesa python
datos = json.loads(texto_limpio)


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 4 — Acceder a los campos del JSON
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: una vez parseado, "datos" es un diccionario Python normal.
# Accedes a sus campos con datos["nombre_del_campo"].
# Los nombres de los campos dependen de lo que definiste en tu system prompt.
#
# Pista: tu system prompt debería haber definido campos como:
#        numero_pedido, tipo_problema, urgencia, resumen
#        Accede a tres de ellos para imprimir el resultado.
#
# Completa (usa los nombres de campo que pusiste en tu system prompt):
print("=" * 50)
print("Ticket clasificado:")
print("=" * 50)
print(f"# Pedido:    {datos['numero_pedido']}")
print(f"Estado percibido del pedido:  {datos['estado_percibido_pedido']}")
print(f"Urgencia:  {datos['sentido_de_urgencia']}")
print()
print("JSON completo:")
print(json.dumps(datos, indent=2, ensure_ascii=False))
print()
print(f"[Meta] Tokens — entrada: {respuesta.usage.input_tokens} | salida: {respuesta.usage.output_tokens}")
