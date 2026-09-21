"""
Fase 10 — Proyecto final, parte 2: evaluación final del orquestador
===================================================================
Objetivo: decidir con evidencia si el orquestador (ejercicio 1) está listo. Se evalúa en dos partes:

  A. GUARDRAILS (sin API): son código puro, así que se prueban con certeza y siempre deben pasar.
  B. CASOS DE PUNTA A PUNTA (con la API real): consultas, traspasos, rechazo humano, memoria de
     hilo en varios turnos, tool caída, API caída y presupuesto agotado. Cada caso verifica ruta,
     tools intentadas, efectos reales y la forma de terminar.

Como el LLM no es determinista, la parte B se corre REPETICIONES veces y el proyecto solo se da
por bueno si TODAS las pasadas superan el UMBRAL (estabilidad, no suerte). Un caso que revienta
con un traceback cuenta como fallo, pero el eval sigue con los demás.

Ejecutar (desde la raíz del repo), después de resolver el ejercicio 1:
    python ejercicios/fase_10/ejercicio_2.py        → código de salida 0 (listo) o 1 (no listo)

Este archivo importa `ejercicio_1` (el orquestador) y le cambia piezas en caliente para forzar
fallas: el cliente (API caída) y PRESUPUESTO_TOKENS. Se restauran siempre al terminar cada caso.
"""

import sys
import uuid

import anthropic

import ejercicio_1 as orq

REPETICIONES = 3
UMBRAL = 0.8  # fracción mínima de casos que deben pasar en CADA pasada

# Cada caso:
#   mensajes    → los turnos del usuario, en el MISMO hilo (memoria)
#   agente      → primer agente elegido por el supervisor
#   termina_en  → (opcional) último agente de la traza, para los traspasos
#   tools       → (opcional) conjunto de tools de negocio que se INTENTARON usar
#   reclamos    → cuántos reclamos deben haberse CREADO de verdad
#   aprobar     → qué decide el "humano automático" cuando se le pide aprobación
#   stop_reason → (opcional) cómo debe terminar el grafo
#   responde_con→ (opcional) texto que debe aparecer en la respuesta final
#   presupuesto / falla_api → fallas que se inyectan
CASOS = [
    {"nombre": "consulta de pedido", "mensajes": ["¿Cómo va mi pedido RP-1001?"],
     "agente": "pedidos", "tools": {"consultar_estado_pedido"}, "reclamos": 0},
    {"nombre": "consulta de pago", "mensajes": ["¿Ya me cobraron el pedido RP-1002?"],
     "agente": "pagos", "tools": {"consultar_pago"}, "reclamos": 0},
    {"nombre": "queja aprobada", "mensajes": ["Mi pedido RP-1002 llegó frío y quiero registrar un reclamo"],
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 1, "aprobar": True},
    {"nombre": "queja rechazada por el humano", "mensajes": ["Mi pedido RP-1003 llegó incompleto y quiero registrar un reclamo"],
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 0, "aprobar": False},
    {"nombre": "traspaso pagos → reclamos",
     "mensajes": ["¿Por qué me cobraron dos veces el pedido RP-1001? Si es así, regístrame un reclamo."],
     "agente": "pagos", "termina_en": "reclamos", "reclamos": 1, "aprobar": True},
    {"nombre": "memoria de hilo (2 turnos)",
     "mensajes": ["Mi pedido llegó frío y quiero registrar un reclamo", "Es el pedido RP-1002"],
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 1, "aprobar": True},
    {"nombre": "tool caída (RP-9999)", "mensajes": ["¿Cómo va mi pedido RP-9999?"],
     "agente": "pedidos", "tools": {"consultar_estado_pedido"}, "reclamos": 0},
    {"nombre": "API caída", "mensajes": ["Hola, ¿cómo va mi pedido RP-1001?"],
     "agente": "pedidos", "tools": set(), "reclamos": 0, "falla_api": True,
     "stop_reason": "error", "responde_con": "problema técnico"},
    {"nombre": "presupuesto agotado", "mensajes": ["Mi pedido RP-1003 llegó incompleto, registra el reclamo"],
     "agente": "reclamos", "reclamos": 0, "aprobar": True, "presupuesto": 1, "stop_reason": "limite"},
]


def pruebas_guardrails() -> bool:
    """Parte A — sin API. Los guardrails son código: se verifican con certeza."""
    invalido = {"type": "tool_use", "id": "x", "name": "crear_reclamo",
                "input": {"numero_pedido": "el de ayer", "motivo": "llegó frío"}}
    valido = {"type": "tool_use", "id": "y", "name": "crear_reclamo",
              "input": {"numero_pedido": "RP-1002", "motivo": "llegó frío"}}

    # -------------------------------------------------------------------
    # BLANK 1 y 2 — Los guardrails, sin depender del modelo
    # -------------------------------------------------------------------
    # 1: `rechaza_invalido` es True si `validar_argumentos` (del orquestador) devuelve un mensaje
    #    de error (no None) para la llamada inválida.
    # 2: `no_molesta` es True si `requiere_aprobacion` dice que la llamada inválida NO necesita
    #    aprobación (no se le pregunta al humano por algo que se va a rechazar igual).
    #
    # Pregunta para razonar: ¿por qué esto se prueba sin la API y no como un caso más de CASOS?
    rechaza_invalido = ___BLANK_1___
    no_molesta = ___BLANK_2___
    pide_aprobacion = orq.requiere_aprobacion(valido)
    lectura_sin_aprobacion = not orq.requiere_aprobacion(
        {"type": "tool_use", "id": "z", "name": "consultar_pago", "input": {"numero_pedido": "RP-1001"}}
    )
    resultados = {
        "rechaza args inválidos": rechaza_invalido,
        "no molesta al humano por inválidas": no_molesta,
        "pide aprobación si es válida": pide_aprobacion,
        "lecturas no piden aprobación": lectura_sin_aprobacion,
    }
    print("A. Guardrails (sin API)")
    for nombre, ok in resultados.items():
        print(f"  {'✓' if ok else '✗'} {nombre}")
    return all(resultados.values())


def evaluar_caso(caso: dict) -> dict:
    orq.RECLAMOS.clear()  # cada caso parte sin reclamos previos
    presupuesto_original = orq.PRESUPUESTO_TOKENS
    cliente_original = orq.cliente
    if "presupuesto" in caso:
        orq.PRESUPUESTO_TOKENS = caso["presupuesto"]
    if caso.get("falla_api"):
        # -------------------------------------------------------------------
        # BLANK 3 — Simular una API caída
        # -------------------------------------------------------------------
        # 3: un cliente de Anthropic apuntando a una dirección donde no hay nadie:
        #    base_url="http://localhost:9", sin reintentos (max_retries=0) y timeout de 2.0 s.
        #    Así la falla es inmediata y el eval no espera.
        orq.cliente = ___BLANK_3___
    thread_id = str(uuid.uuid4())  # UN hilo por caso: todos sus turnos comparten memoria
    try:
        for mensaje in caso["mensajes"]:
            # ---------------------------------------------------------------
            # BLANK 4 — Cada turno del caso, en el mismo hilo
            # ---------------------------------------------------------------
            # 4: guarda en `resultado` lo que devuelve `orq.hablar` con el thread_id, el mensaje y
            #    una función que decide la aprobación: lambda acciones: caso.get("aprobar", True).
            resultado = ___BLANK_4___
    except Exception as e:  # un traceback = caso fallido, pero el eval continúa
        return {"ok": False, "detalle": {"sin_caida": False}, "traza": [], "tools_usadas": set(),
                "error": f"{type(e).__name__}: {e}"}
    finally:
        orq.PRESUPUESTO_TOKENS = presupuesto_original
        orq.cliente = cliente_original

    tools_usadas = {
        b["name"]
        for m in resultado["historial"]
        if m["role"] == "assistant"
        for b in m["content"]
        if b["type"] == "tool_use" and b["name"] != "transferir_a"
    }
    traza = resultado["traza"]

    # -------------------------------------------------------------------
    # BLANK 5 y 6 — Ruta y efectos
    # -------------------------------------------------------------------
    # 5: `ok_ruta`: el PRIMER agente de la traza es caso["agente"] Y el ÚLTIMO es
    #    caso.get("termina_en", traza[-1]) (si el caso no lo define, no se exige nada).
    # 6: `ok_efectos`: los reclamos realmente creados (len(orq.RECLAMOS)) son caso["reclamos"].
    #
    # Pregunta para razonar: ¿por qué en "queja rechazada" verificar EFECTOS es más importante
    # que leer lo que el agente responde?
    ok_ruta = ___BLANK_5___
    ok_efectos = ___BLANK_6___
    ok_tools = caso.get("tools") is None or tools_usadas == caso["tools"]
    ok_final = (
        resultado["stop_reason"] == caso.get("stop_reason", resultado["stop_reason"])
        and caso.get("responde_con", "") in resultado["respuesta"].lower()
    )
    detalle = {"ruta": ok_ruta, "tools": ok_tools, "efectos": ok_efectos, "final": ok_final}
    return {"ok": all(detalle.values()), "detalle": detalle, "traza": traza, "tools_usadas": tools_usadas}


def correr_pasada(numero: int) -> float:
    print(f"\nB. Casos de punta a punta — pasada {numero}/{REPETICIONES}")
    aciertos = 0
    for caso in CASOS:
        print(f"\n▶ {caso['nombre']}")
        r = evaluar_caso(caso)
        aciertos += r["ok"]
        if "error" in r:
            print(f"  ✗ se cayó: {r['error']}")
        else:
            marca = "✓" if r["ok"] else "✗"
            print(f"  {marca} {r['detalle']}  ruta={' → '.join(r['traza'])}  tools={sorted(r['tools_usadas'])}")
    precision = aciertos / len(CASOS)
    print(f"\n  Pasada {numero}: {aciertos}/{len(CASOS)} ({precision:.0%})")
    return precision


def main() -> int:
    guardrails_ok = pruebas_guardrails()
    precisiones = [correr_pasada(n) for n in range(1, REPETICIONES + 1)]

    # -------------------------------------------------------------------
    # BLANK 7 — La puerta de calidad final
    # -------------------------------------------------------------------
    # 7: `listo` es True si los guardrails pasaron Y CADA pasada alcanzó el UMBRAL (no el promedio:
    #    una pasada mala es una señal de inestabilidad).
    listo = ___BLANK_7___
    print("\n" + "=" * 60)
    print(f"Guardrails: {'OK' if guardrails_ok else 'FALLA'} · pasadas: {[f'{p:.0%}' for p in precisiones]} · umbral {UMBRAL:.0%}")
    print("RESULTADO:", "LISTO PARA PRODUCCIÓN" if listo else "NO LISTO: revisa prompts, umbrales y trazas")
    return 0 if listo else 1


if __name__ == "__main__":
    sys.exit(main())
