"""Dobles de prueba para correr todo el harness SIN la API (tests, CI y evals de humo).

`FakeLLM` no entiende lenguaje: aplica reglas simples de soporte de pedidos según las tools que ve
el agente. Sirve para verificar la FONTANERÍA (rutas, aprobación, traspasos, hilos, límites), no la
calidad de las respuestas: para eso están los evals contra la API real.
"""

from __future__ import annotations

import itertools
import re

from .harness.window import es_inicio_de_turno, validar_historial
from .llm import LLMError, Respuesta

_PEDIDO = re.compile(r"RP-\d{4}")


def _texto_usuario(m: dict) -> str | None:
    return m["content"] if es_inicio_de_turno(m) and isinstance(m["content"], str) else None


def _uso(nombre: str, args: dict, ids) -> dict:
    return {"type": "tool_use", "id": f"tu_{next(ids)}", "name": nombre, "input": args}


class FakeLLM:
    def __init__(self, falla: bool = False, tokens_por_llamada: int = 100, estricto: bool = True):
        # estricto: simula el error 400 de la API si el historial recibido no es válido
        self.falla, self.tokens, self.estricto = falla, tokens_por_llamada, estricto
        self.llamadas: list[dict] = []
        self._ids = itertools.count(1)

    def crear(self, *, system, messages, tools, max_tokens, tool_choice=None) -> Respuesta:
        self.llamadas.append({"system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice})
        if self.falla:
            raise LLMError("caída simulada")
        if tool_choice and tool_choice.get("name") == "elegir_agente":
            previo, texto = messages[-1]["content"].split("\nMensaje nuevo:", 1)
            previo, texto = previo.split(": ", 1)[-1].strip(), texto.lower()
            if any(p in texto for p in ("cobr", "pago")):
                agente = "pagos"
            elif any(p in texto for p in ("reclam", "frío", "incompleto")):
                agente = "reclamos"
            elif any(p in texto for p in ("cómo va", "estado")):
                agente = "pedidos"
            else:  # seguimiento sin tema nuevo: conserva el agente previo, como pide el prompt real
                agente = previo if previo != "ninguno" else "pedidos"
            return Respuesta([_uso("elegir_agente", {"agente": agente}, self._ids)], "tool_use", self.tokens)
        if self.estricto and not validar_historial(messages):
            raise AssertionError("400 simulado: historial inválido (tool_use sin tool_result, roles mal alternados…)")
        return self._especialista(messages, [t["name"] for t in tools])

    def _especialista(self, messages: list[dict], tools: list[str]) -> Respuesta:
        inicio = max(i for i, m in enumerate(messages) if es_inicio_de_turno(m))
        turno = messages[inicio:]
        textos = [t for t in (_texto_usuario(m) for m in messages) if t]
        pedidos = _PEDIDO.findall(" ".join(textos))
        pedido = pedidos[-1] if pedidos else None
        usados = [b["name"] for m in turno if m["role"] == "assistant" and not isinstance(m["content"], str)
                  for b in m["content"] if b["type"] == "tool_use"]
        ultimo = messages[-1]
        ultimo_res = ultimo["content"][0] if ultimo["role"] == "user" and not isinstance(ultimo["content"], str) else None
        fallo = bool(ultimo_res and ultimo_res.get("is_error"))

        def texto(t):
            return Respuesta([{"type": "text", "text": t}], "end_turn", self.tokens)

        def llamar(nombre, args):
            return Respuesta([_uso(nombre, args, self._ids)], "tool_use", self.tokens)

        if not pedido:
            return texto("¿Me compartes el número de tu pedido?")
        if "crear_reclamo" in tools:  # rol: reclamos
            if "consultar_estado_pedido" not in usados:
                return llamar("consultar_estado_pedido", {"numero_pedido": pedido})
            if fallo and "crear_reclamo" not in usados:
                return texto("Tuve un problema técnico consultando tu pedido; un agente humano te contactará.")
            if "crear_reclamo" not in usados:
                return llamar("crear_reclamo", {"numero_pedido": pedido, "motivo": textos[0]})
            if fallo:
                return texto("No se pudo registrar el reclamo; un agente humano te contactará.")
            rid = re.search(r"REC-\d+", ultimo_res["content"]).group()
            return texto(f"Lamento lo ocurrido. Registré tu reclamo {rid}.")
        if "consultar_pago" in tools:  # rol: pagos
            if "consultar_pago" not in usados and "transferir_a" not in usados:
                return llamar("consultar_pago", {"numero_pedido": pedido})
            if "reclamo" in " ".join(textos[-1:]).lower() and "transferir_a" in tools and "transferir_a" not in usados:
                return llamar("transferir_a", {"agente": "reclamos", "motivo": "cobro duplicado; el cliente quiere reclamar"})
            return texto("Ya revisé tus cobros de ese pedido.")
        if "consultar_estado_pedido" in tools:  # rol: pedidos
            if "consultar_estado_pedido" not in usados:
                return llamar("consultar_estado_pedido", {"numero_pedido": pedido})
            if fallo:
                return texto("Hay un problema técnico con el sistema de pedidos; intenta más tarde.")
            return texto(f"Tu pedido {pedido} está en camino.")
        return texto("Hola, ¿en qué te ayudo?")
