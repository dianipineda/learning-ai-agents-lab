"""
Fase 9 — Ejercicio 1: Evaluación (¿mi cambio de prompt mejora o empeora al agente?)
===================================================================================
Objetivo: dejar de decidir "a ojo" si un prompt es mejor. Una EVALUACIÓN (eval) es un
conjunto fijo de casos con la respuesta esperada y un script que los corre y saca una
métrica. Así, cada vez que cambias un prompt, corres el eval y comparas números.

Qué evaluamos aquí: el CLASIFICADOR de solicitudes (el mismo de las fases 7 y 8). Es el
mejor primer objetivo: su salida es un JSON pequeño y se puede comparar de forma exacta.

Tienes dos versiones del prompt:
  - PROMPT_A: mínimo, sin definiciones.
  - PROMPT_B: con definiciones de cada tipo y reglas para el número de pedido.
El script corre los mismos casos contra ambas y te dice cuál gana y en qué casos falla.

Ojo: el LLM no es 100 % determinista. Una diferencia de un caso puede ser ruido. Corre el
eval un par de veces antes de sacar conclusiones, y usa más casos cuando la diferencia sea chica.
"""

import json
from dotenv import load_dotenv

import anthropic

load_dotenv()

cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)
MODELO = "claude-sonnet-5"

PROMPT_A = """
Clasifica el mensaje de un cliente de soporte de pedidos.
Devuelve ÚNICAMENTE JSON: { "tipo": "consulta_pedido" | "queja" | "saludo" | "otro", "numero_pedido": "<número o null>" }
"""

PROMPT_B = """
Eres un clasificador de solicitudes de soporte de pedidos. Devuelve ÚNICAMENTE JSON, sin texto
extra ni bloques Markdown:
{ "tipo": "consulta_pedido" | "queja" | "saludo" | "otro", "numero_pedido": "<número o null>" }

Definiciones:
- consulta_pedido: el cliente pregunta el estado o la ubicación de un pedido, sin expresar molestia.
- queja: el cliente expresa un problema o molestia (pedido frío, incompleto, cobro de más,
  demora excesiva) o pide reclamar, aunque también mencione el estado.
- saludo: solo saluda o se despide.
- otro: cualquier cosa que no tenga que ver con pedidos.
El número de pedido tiene formato RP-1234. Si el mensaje no lo trae, usa null (no lo inventes).
"""

# -------------------------------------------------------------------
# Dataset: cada caso tiene el mensaje y la respuesta ESPERADA (la "etiqueta").
# -------------------------------------------------------------------
# BLANK 1 — Escribe tú mismo la etiqueta del último caso.
#   Mensaje: "Mi pedido RP-1003 llegó frío y quiero reclamar"
#   1a: el `tipo` esperado.   1b: el `numero_pedido` esperado (string).
#
# Pregunta para razonar: ¿qué pasa con la métrica si una etiqueta está mal puesta?
CASOS = [
    {"mensaje": "Hola, buenas tardes", "tipo": "saludo", "numero_pedido": None},
    {"mensaje": "¿Cómo va mi pedido RP-1001?", "tipo": "consulta_pedido", "numero_pedido": "RP-1001"},
    {"mensaje": "Mi pedido RP-1002 llegó frío y quiero poner una queja", "tipo": "queja", "numero_pedido": "RP-1002"},
    {"mensaje": "Quiero saber dónde está mi orden RP-1003", "tipo": "consulta_pedido", "numero_pedido": "RP-1003"},
    {"mensaje": "Esto es inaceptable, llevo una hora esperando el RP-1001", "tipo": "queja", "numero_pedido": "RP-1001"},
    {"mensaje": "¿Me recomiendas un restaurante para esta noche?", "tipo": "otro", "numero_pedido": None},
    {"mensaje": "Me cobraron doble el pedido RP-1002", "tipo": "queja", "numero_pedido": "RP-1002"},
    {"mensaje": "Buenos días", "tipo": "saludo", "numero_pedido": None},
    {"mensaje": "Mi comida llegó incompleta, faltó la bebida (RP-1001)", "tipo": "queja", "numero_pedido": "RP-1001"},
    {"mensaje": "Quiero poner una queja pero no recuerdo mi número de pedido", "tipo": "queja", "numero_pedido": None},
    {"mensaje": "¿Cuál es el estado del RP-1002?", "tipo": "consulta_pedido", "numero_pedido": "RP-1002"},
    {"mensaje": "Mi pedido RP-1003 llegó frío y quiero reclamar", "tipo": "queja", "numero_pedido": "RP-1003"},
]


def clasificar(system: str, mensaje: str) -> dict:
    """Corre el clasificador con un prompt dado. Devuelve {} si la salida no es JSON válido."""
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": mensaje}],
    )
    texto = next(b.text for b in respuesta.content if b.type == "text").strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(texto)
    except ValueError:
        return {}


# -------------------------------------------------------------------
# BLANK 2 — ¿Acertó este caso?
# -------------------------------------------------------------------
# Un caso se da por bueno solo si el `tipo` Y el `numero_pedido` obtenidos coinciden con los
# esperados. `obtenido` es el dict que devolvió el clasificador (puede ser {} si falló).
#
# Pista: usa `.get()` sobre `obtenido` para que un JSON incompleto no lance KeyError.
def acerto(caso: dict, obtenido: dict) -> bool:
    return obtenido.get("tipo") == caso["tipo"] and obtenido.get("numero_pedido") == caso["numero_pedido"]


def evaluar(system: str) -> dict:
    """Corre todos los casos con un prompt. Devuelve la precisión y la lista de fallos."""
    fallos = []
    aciertos = 0
    for caso in CASOS:
        obtenido = clasificar(system, caso["mensaje"])
        if acerto(caso, obtenido):
            aciertos += 1
        else:
            fallos.append({"mensaje": caso["mensaje"], "esperado": (caso["tipo"], caso["numero_pedido"]),
                           "obtenido": (obtenido.get("tipo"), obtenido.get("numero_pedido"))})
    # -------------------------------------------------------------------
    # BLANK 3 — La métrica
    # -------------------------------------------------------------------
    # Precisión = fracción de casos acertados (un número entre 0 y 1).
    precision = aciertos / len(CASOS)
    return {"precision": precision, "fallos": fallos}


# -------------------------------------------------------------------
# BLANK 4 — Correr el mismo eval contra cada prompt
# -------------------------------------------------------------------
# `resultados` debe ser un dict {nombre_del_prompt: resultado_de_evaluar(ese_prompt)}.
# Pista: una comprensión de diccionario sobre PROMPTS.items().
PROMPTS = {"A (mínimo)": PROMPT_A, "B (con definiciones)": PROMPT_B}

print(f"Evaluando {len(CASOS)} casos por prompt...\n")
resultados = {nombre: evaluar(system) for nombre, system in PROMPTS.items()}

for nombre, r in resultados.items():
    print(f"Prompt {nombre}: precisión {r['precision']:.0%}")
    for f in r["fallos"]:
        print(f"    ✗ {f['mensaje']!r}\n        esperado={f['esperado']}  obtenido={f['obtenido']}")

# -------------------------------------------------------------------
# BLANK 5 — ¿Cuál gana?
# -------------------------------------------------------------------
# `mejor` debe ser el NOMBRE del prompt con mayor precisión.
# Pista: max() sobre las llaves de `resultados`, con `key=` que mire la precisión.
mejor = max(resultados, key=lambda nombre: resultados[nombre]["precision"])
print(f"\nGana: {mejor}")

# -------------------------------------------------------------------
# BLANK 6 — Puerta de calidad (regression gate)
# -------------------------------------------------------------------
# En un flujo real el eval se corre antes de cambiar un prompt en producción. Aquí simulamos
# la puerta: el prompt B es el "candidato" y solo se acepta si NO empeora respecto al A.
# 6: la condición booleana `acepta_candidato` (precisión de B >= precisión de A).
#
# Pregunta para razonar: ¿por qué >= y no >? ¿Y por qué una sola corrida puede engañar?
acepta_candidato = resultados["B (con definiciones)"]["precision"] >= resultados["A (mínimo)"]["precision"]
print("Candidato B aceptado" if acepta_candidato else "Candidato B RECHAZADO: empeora al actual")
