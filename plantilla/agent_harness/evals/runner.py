"""Evaluación con puerta de calidad.

  A. GUARDRAILS (sin modelo): código puro, deben pasar siempre.
  B. CASOS de punta a punta, repetidos N veces: el LLM no es determinista, así que se exige que TODAS
     las pasadas superen el umbral (estabilidad, no suerte). Un caso que revienta cuenta como fallo
     pero el eval sigue.

Las fallas se INYECTAN por construcción (LLM caído, presupuesto mínimo), no con monkeypatch.
"""

from __future__ import annotations

import uuid
from typing import Callable

from ..app import App, crear_app
from ..config import Settings
from ..llm import LLM, LLMError, Respuesta
from ..textos import TEXTO_FALLA
from .casos import CASOS

Fabrica = Callable[[Settings, LLM | None], App]


class LLMCaido:
    def crear(self, **_) -> Respuesta:
        raise LLMError("API caída (inyectada)")


def pruebas_guardrails(app: App) -> bool:
    reg = app.orquestador.registry
    crear = reg.get("crear_reclamo")
    chequeos = {
        "pedido con formato inválido se rechaza": reg.get("consultar_estado_pedido").validar_args({"numero_pedido": "XX-1"}) is not None,
        "motivo vacío se rechaza": crear.validar_args({"numero_pedido": "RP-1001", "motivo": "  "}) is not None,
        "falta un argumento obligatorio": crear.validar_args({"numero_pedido": "RP-1001"}) is not None,
        "crear_reclamo válido se acepta": crear.validar_args({"numero_pedido": "RP-1001", "motivo": "frío"}) is None,
        "crear_reclamo es sensible (exige aprobación)": crear.sensible,
        "consultar_estado_pedido no es sensible": not reg.get("consultar_estado_pedido").sensible,
    }
    for nombre, ok in chequeos.items():
        print(f"  {'✓' if ok else '✗'} {nombre}")
    return all(chequeos.values())


def evaluar_caso(caso: dict, fabrica: Fabrica, settings: Settings, llm: LLM | None = None) -> bool:
    if caso.get("presupuesto") is not None:
        settings = settings.con(presupuesto_tokens=caso["presupuesto"])
    app = fabrica(settings, LLMCaido() if caso.get("falla_api") else llm)
    orq, thread_id = app.orquestador, str(uuid.uuid4())
    intentadas: set[str] = set()
    ultimo: dict = {}
    for mensaje in caso["mensajes"]:
        for ev in orq.eventos(thread_id, mensaje, lambda acciones: caso.get("aprobar", True)):
            if ev["tipo"] == "progreso" and ev.get("tool"):
                intentadas.add(ev["tool"])
            if ev["tipo"] == "final":
                ultimo = ev["estado"]
    traza = ultimo.get("traza", [])
    negocio = {t for t in intentadas if t != "transferir_a"}
    checks = {
        "ruta": bool(traza) and traza[0] == caso["agente"] and traza[-1] == caso.get("termina_en", traza[-1]),
        "tools": negocio == caso["tools"] if "tools" in caso else True,
        "efectos": len(app.backend.reclamos) == caso["reclamos"],
        "final": (ultimo.get("stop_reason") == caso["stop_reason"] if "stop_reason" in caso else True)
                 and (caso["responde_con"].lower() in ultimo.get("respuesta", "").lower() if "responde_con" in caso else True),
    }
    print(f"    {'✓' if all(checks.values()) else '✗'} {caso['nombre']:<34} " + " ".join(f"{k}={'ok' if v else 'FALLA'}" for k, v in checks.items()))
    return all(checks.values())


def evaluar(fabrica: Fabrica = crear_app, settings: Settings | None = None, llm: LLM | None = None,
            repeticiones: int = 3, umbral: float = 0.8) -> bool:
    settings = settings or Settings.from_env()
    print("A. Guardrails (sin modelo)")
    guardrails_ok = pruebas_guardrails(fabrica(settings, llm))
    precisiones = []
    for n in range(1, repeticiones + 1):
        print(f"B. Casos de punta a punta — pasada {n}/{repeticiones}")
        aciertos = 0
        for caso in CASOS:
            try:
                aciertos += evaluar_caso(caso, fabrica, settings, llm)
            except Exception as e:  # un caso roto cuenta como fallo, el eval sigue
                print(f"    ✗ {caso['nombre']:<34} EXCEPCIÓN {type(e).__name__}: {e}")
        precisiones.append(aciertos / len(CASOS))
        print(f"    precisión: {aciertos}/{len(CASOS)} = {precisiones[-1]:.0%}")
    listo = guardrails_ok and all(p >= umbral for p in precisiones)
    print(f"\n{'LISTO PARA PRODUCCIÓN' if listo else 'NO LISTO'} (guardrails={'ok' if guardrails_ok else 'FALLA'}, "
          f"pasadas={[f'{p:.0%}' for p in precisiones]}, umbral={umbral:.0%})")
    return listo
