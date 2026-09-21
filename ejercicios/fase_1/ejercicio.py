# =============================================================================
# FASE 1 — Tu primera llamada a un LLM
# Objetivo: hacer que Python hable con Claude y reciba una respuesta
# =============================================================================
#
# INSTRUCCIONES:
#   Hay 5 blancos marcados con ___BLANK_X___
#   Cada uno tiene una pista y un concepto que estás practicando.
#   Completa los blancos, luego corre: python fase_1/ejercicio.py
#
# =============================================================================

import os
from dotenv import load_dotenv

# Carga las variables del archivo .env (tu API key vive ahí)
load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 1 — Importar el paquete correcto
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: una API client library es un paquete que te da una interfaz
# cómoda para hablar con un servicio externo sin construir las llamadas HTTP tú mismo.
#
# Pista: el paquete se llama igual que la empresa que hace Claude.
#        Ya lo instalaste con requirements.txt.
#
# Completa:
___BLANK_1___


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 2 — Crear el cliente
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: el "cliente" es el objeto que representa tu conexión con la API.
# Se autentica con tu API key (que está en la variable de entorno ANTHROPIC_API_KEY).
#
# Pista: es una clase que se llama igual que el paquete que importaste,
#        con la primera letra en mayúscula. No necesitas pasarle la key
#        manualmente — la lee sola del entorno si se llama ANTHROPIC_API_KEY.
#
# Completa:
cliente = ___BLANK_2___
# Recuerda: tu clave exige el header default_headers={"anthropic-workspace-id": "wrkspc_..."} (ver README)


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 3 — Construir el mensaje
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: los LLMs esperan los mensajes en un formato específico.
# Cada mensaje tiene DOS campos obligatorios: quién lo manda y qué dice.
#
# Pista: los dos roles posibles en una conversación simple son
#        quien pregunta y quien responde. Tú eres quien pregunta.
#
# Completa los dos campos del diccionario:
messages = [
    ___BLANK_3___
    # NOTA — ¿cuándo usar "assistant"?
    # Los LLMs no tienen memoria entre llamadas. Si quieres una conversación
    # de múltiples turnos, tú eres responsable de reenviar el historial completo.
    # Cada respuesta que Claude dio en turnos anteriores va con role="assistant":
    #
    #   {"role": "user",      "content": "¿Capital de Francia?"},
    #   {"role": "assistant", "content": "París."},          ← lo que Claude respondió antes
    #   {"role": "user",      "content": "¿Cuántos habitantes?"},
    #
    # Regla: "user" = tú hablas | "assistant" = Claude habló (historial)
]


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 4 — Llamar al modelo
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: max_tokens limita cuánto puede responder el modelo.
# Si pones 10, solo recibes ~10 tokens (unas pocas palabras).
# Si pones 1024, le das espacio para responder con detalle.
#
# Pista: el modelo más reciente y capaz de Anthropic para uso general
#        es claude-sonnet-5 (revisa la guía de conceptos si no recuerdas).
#        Para una respuesta corta como esta, 256 tokens es más que suficiente.
#
# Completa:
respuesta = cliente.messages.create(
    model=___BLANK_4a___,
    max_tokens=___BLANK_4b___,
    messages=messages
)


# ─────────────────────────────────────────────────────────────────────────────
# BLANK 5 — Extraer el texto de la respuesta
# ─────────────────────────────────────────────────────────────────────────────
# Concepto: la respuesta de la API no es solo texto — es un objeto con
# metadatos (tokens usados, modelo, razón de parada, etc.).
# El texto real vive dentro de una lista llamada "content".
# Cada elemento de esa lista tiene un campo "text" con el texto generado.
#
# Pista: la respuesta tiene una propiedad .content que es una lista.
#        El primer elemento [0] tiene una propiedad .text
#
# Completa:
texto = ___BLANK_5___

print("=" * 50)
print("Respuesta de Claude:")
print("=" * 50)
print(texto)
print()
print(f"[Meta] Tokens usados — entrada: {respuesta.usage.input_tokens} | salida: {respuesta.usage.output_tokens}")
