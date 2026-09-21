"""
Fase 7 — Ejercicio 1: Grafo mínimo en LangGraph
================================================
Objetivo: entender el modelo mental de LangGraph con el grafo más pequeño posible.

  START → [clasificar] → END

Conceptos:
  - STATE: un dict tipado que viaja por todo el grafo (reemplaza tus variables sueltas
    como `historial` y `clasificacion`).
  - NODO: una función que RECIBE el state y DEVUELVE solo los campos que cambia.
    LangGraph mezcla ese dict parcial con el state; tú no lo reconstruyes entero.
  - EDGE: una conexión "después de A corre B". START y END son nodos especiales.
  - compile() → convierte el builder en un objeto ejecutable; invoke() lo corre.

Nota: aquí NO usamos langchain-anthropic. Los nodos siguen llamando al SDK de
Anthropic como en las fases 1-6. LangGraph solo orquesta; no te obliga a usar LangChain.
"""

import json
from typing import TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)

MODELO = "claude-sonnet-5"

SYSTEM_CLASIFICADOR = """
Eres un clasificador de solicitudes de soporte de pedidos. Devuelve ÚNICAMENTE JSON:
{ "tipo": "consulta_pedido" | "queja" | "saludo" | "otro", "numero_pedido": "<número o null>" }
Sin texto extra ni bloques Markdown.
"""


# -------------------------------------------------------------------
# BLANK 1 — Definir el State
# -------------------------------------------------------------------
# El state es una clase que hereda de TypedDict. Declara dos campos:
#   - mensaje: str          (lo que escribió el usuario; entra al grafo)
#   - clasificacion: dict   (lo que produce el nodo; sale del grafo)
#
# Pista: es como un dict con claves fijas y tipos:
#   class Estado(TypedDict):
#       campo: tipo
class Estado(TypedDict):
    ___BLANK_1___


# -------------------------------------------------------------------
# BLANK 2 — El nodo `clasificar`
# -------------------------------------------------------------------
# Un nodo es una función normal: recibe `estado` y devuelve un dict PARCIAL
# con los campos que quiere actualizar. Aquí solo actualiza "clasificacion".
#
# El cuerpo ya casi está: es tu clasificar_mensaje de la Fase 6, pero leyendo el
# mensaje desde el state. Completa el `return`.
#
# Pregunta para razonar: ¿por qué devolvemos {"clasificacion": ...} y no todo el
# estado completo, incluyendo "mensaje"?
def clasificar(estado: Estado) -> dict:
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=SYSTEM_CLASIFICADOR,
        messages=[{"role": "user", "content": estado["mensaje"]}],
    )
    texto = next(b.text for b in respuesta.content if b.type == "text").strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    clasificacion = json.loads(texto)

    return ___BLANK_2___


# -------------------------------------------------------------------
# BLANK 3 — Crear el builder y registrar el nodo
# -------------------------------------------------------------------
# 1. Crea el builder pasándole la CLASE del state:   StateGraph(Estado)
# 2. Registra el nodo con un nombre y la función:    builder.add_node("nombre", funcion)
#
# Pista: el nombre es un string libre; es el que usarás en los edges.
builder = ___BLANK_3a___
___BLANK_3b___


# -------------------------------------------------------------------
# BLANK 4 — Conectar con edges
# -------------------------------------------------------------------
# Conecta START → "clasificar" y "clasificar" → END.
#
# Pista: builder.add_edge(origen, destino)
___BLANK_4a___
___BLANK_4b___


# -------------------------------------------------------------------
# BLANK 5 — Compilar y ejecutar
# -------------------------------------------------------------------
# compile() valida el grafo (nodos huérfanos, edges rotos) y devuelve un objeto
# ejecutable. invoke() recibe el state INICIAL (solo los campos de entrada) y
# devuelve el state FINAL.
#
# Pista: grafo = builder.compile()   /   grafo.invoke({"mensaje": ...})
grafo = ___BLANK_5a___

print("Grafo mínimo LangGraph — escribe 'salir' para terminar\n")

while True:
    user_input = input("Tú: ").strip()
    if user_input.lower() == "salir":
        print("¡Hasta luego!")
        break

    estado_final = ___BLANK_5b___

    print(f"\n  state final → {estado_final}\n")
