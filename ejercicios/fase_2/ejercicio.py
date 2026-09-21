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
SYSTEM_PROMPT = """___BLANK_1___"""


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
    ___BLANK_2___=SYSTEM_PROMPT,
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
datos = ___BLANK_3___


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
print(f"# Pedido:    {___BLANK_4a___}")
print(f"Estado percibido del pedido:  {___BLANK_4b___}")
print(f"Urgencia:  {___BLANK_4c___}")
print()
print("JSON completo:")
print(json.dumps(datos, indent=2, ensure_ascii=False))
print()
print(f"[Meta] Tokens — entrada: {respuesta.usage.input_tokens} | salida: {respuesta.usage.output_tokens}")
