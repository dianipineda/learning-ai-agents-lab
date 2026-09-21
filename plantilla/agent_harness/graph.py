"""El orquestador: supervisor + especialistas como grafo de LangGraph, con el harness alrededor.

    START → supervisor → especialista ─┬─ (fin) ─────────────────────→ END
                              ▲        ├─ (presupuesto excedido) → limite → END
                              │        ├─ (transferir_a) → traspasar ─┐
                              │        ├─ (tool sensible válida) → aprobar → tools ─┐
                              │        └─ (otra tool) ─────────────→ tools ─────────┤
                              └───────────────────────────────────────────────────┘

Orden de decisión en `decidir` (importa): presupuesto → traspaso → aprobación → tools.
Con UN solo agente el supervisor no llama al modelo ni se ofrece `transferir_a`: se empieza simple y
se crece a multiagente agregando AgentSpec, sin tocar el grafo.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .agents import AgentSpec, prompt_supervisor
from .config import Settings
from .harness.guardrails import TRANSFERIR, hay_que_aprobar, hay_traspaso, presupuesto_excedido, requiere_aprobacion
from .harness.repair import cerrar_historial
from .harness.runner import ToolRunner
from .harness.safety import SYSTEM_DATOS
from .harness.window import recortar_historial
from .llm import LLM, LLMError
from .memory.checkpointer import crear_checkpointer
from .memory.usuario import MemoriaUsuario, extraer_hechos
from .observability import evento, fijar_thread, restaurar_thread
from .state import Estado
from .textos import TEXTO_CORTE, TEXTO_FALLA
from .tools import ToolRegistry

Aprobador = Callable[[list], bool]


def _escritor():
    try:
        return get_stream_writer()
    except Exception:  # fuera de un grafo en ejecución
        return lambda _evento: None


class Orquestador:
    def __init__(
        self,
        settings: Settings,
        llm: LLM,
        registry: ToolRegistry,
        agentes: list[AgentSpec],
        *,
        contexto: str = "",
        checkpointer: BaseCheckpointSaver | None = None,
        memoria_usuario: MemoriaUsuario | None = None,
        runner: ToolRunner | None = None,
    ):
        if not agentes:
            raise ValueError("Se necesita al menos un agente")
        self.settings, self.llm, self.registry = settings, llm, registry
        self.agentes = {a.name: a for a in agentes}
        if len(self.agentes) != len(agentes):
            raise ValueError("Nombres de agente duplicados")
        for a in agentes:
            registry.schemas(a.tools)  # falla al construir (no en producción) si falta una tool
        self.runner = runner or ToolRunner(registry, settings)
        self.memoria_usuario = memoria_usuario
        self.checkpointer = checkpointer or crear_checkpointer(settings.checkpoint_db)
        self._por_defecto = agentes[0].name
        self._multi = len(agentes) > 1
        self._system_supervisor = prompt_supervisor(agentes, contexto)
        nombres = list(self.agentes)
        self._elegir = {
            "name": "elegir_agente",
            "description": "Elige el agente especialista que debe atender el mensaje.",
            "input_schema": {"type": "object", "properties": {"agente": {"type": "string", "enum": nombres}}, "required": ["agente"]},
        }
        self._transferir = {
            "name": TRANSFERIR,
            "description": (
                "Traspasa la conversación a otro agente cuando el tema corresponde a él. "
                "Indica el motivo y lo que ya sabes, para que no tenga que repreguntar."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"agente": {"type": "string", "enum": nombres},
                               "motivo": {"type": "string", "description": "Por qué se traspasa y qué contexto ya hay"}},
                "required": ["agente", "motivo"],
            },
        }
        self.grafo = self._construir()

    # ------------------------------------------------------------------ nodos
    def supervisor(self, estado: Estado) -> dict:
        previo = estado.get("agente")
        agente, tokens = self._por_defecto, 0
        if self._multi:
            contenido = f"Agente que venía atendiendo: {previo or 'ninguno'}\nMensaje nuevo: {estado['mensaje']}"
            try:
                r = self.llm.crear(
                    system=self._system_supervisor, messages=[{"role": "user", "content": contenido}],
                    tools=[self._elegir], max_tokens=256, tool_choice={"type": "tool", "name": "elegir_agente"},
                )
                elegido = next(b for b in r.content if b["type"] == "tool_use")["input"]["agente"]
                if elegido not in self.agentes:
                    raise KeyError(elegido)
                agente, tokens = elegido, r.tokens
            except (LLMError, StopIteration, KeyError) as e:
                # El supervisor es degradable: si falla, se sigue con el agente previo (o el primero).
                agente = previo if previo in self.agentes else self._por_defecto
                evento("supervisor.degradado", logging.WARNING, error=type(e).__name__, agente=agente)
        evento("supervisor.eligio", agente=agente, previo=previo)
        return {"agente": agente, "traza": [agente], "tokens_usados": tokens, "traspasos": 0, "aprobado": False}

    def especialista(self, estado: Estado) -> dict:
        spec = self.agentes[estado["agente"]]
        tools = self.registry.schemas(spec.tools) + ([self._transferir] if self._multi else [])
        system = spec.system + "\n\n" + SYSTEM_DATOS
        if self.memoria_usuario and estado.get("user_id"):
            contexto = self.memoria_usuario.como_contexto(estado["user_id"])
            system += ("\n\n" + contexto) if contexto else ""
        try:
            r = self.llm.crear(
                system=system, tools=tools, max_tokens=self.settings.max_tokens_agente,
                messages=recortar_historial(estado["historial"], self.settings.ventana_mensajes),
            )
        except LLMError as e:
            evento("llm.fallo", logging.ERROR, agente=spec.name, error=str(e))
            # Sin este mensaje el historial acabaría en `user` y el siguiente turno daría error 400.
            return {"historial": [{"role": "assistant", "content": [{"type": "text", "text": TEXTO_FALLA}]}],
                    "stop_reason": "error", "respuesta": TEXTO_FALLA}
        total = estado.get("tokens_usados", 0) + r.tokens
        evento("agente.respondio", agente=spec.name, stop_reason=r.stop_reason, tokens_turno=r.tokens, tokens_hilo=total)
        return {"historial": [{"role": "assistant", "content": r.content}], "stop_reason": r.stop_reason,
                "respuesta": r.texto, "tokens_usados": r.tokens}

    def aprobar(self, estado: Estado) -> dict:
        acciones = [{"tool": b["name"], "argumentos": b["input"]}
                    for b in estado["historial"][-1]["content"] if requiere_aprobacion(self.registry, b)]
        return {"aprobado": bool(interrupt(acciones))}

    def tools(self, estado: Estado) -> dict:
        aprobado = estado.get("aprobado", False)  # fail closed
        escribir = _escritor()
        resultados = []
        for bloque in estado["historial"][-1]["content"]:
            if bloque["type"] != "tool_use":
                continue
            escribir({"progreso": "tool", "tool": bloque["name"]})
            resultados.append(self.runner.ejecutar(bloque, aprobado))
        return {"historial": [{"role": "user", "content": resultados}]}

    def traspasar(self, estado: Estado) -> dict:
        ultimo = estado["historial"][-1]
        pedido = next(b for b in ultimo["content"] if b["type"] == "tool_use" and b["name"] == TRANSFERIR)
        destino, motivo = pedido["input"].get("agente"), pedido["input"].get("motivo", "")
        hechos = estado.get("traspasos", 0)

        def responder(texto: str, error: bool) -> list[dict]:
            # Todo tool_use del mensaje necesita su tool_result; el traspaso lleva `texto`.
            salida = []
            for b in ultimo["content"]:
                if b["type"] != "tool_use":
                    continue
                if b["id"] == pedido["id"]:
                    salida.append({"type": "tool_result", "tool_use_id": b["id"], "content": texto, "is_error": error})
                else:
                    salida.append({"type": "tool_result", "tool_use_id": b["id"], "is_error": True,
                                   "content": "No ejecutada: hubo un traspaso en el mismo turno. Vuelve a pedirla si aún hace falta."})
            return salida

        if hechos >= self.settings.max_traspasos or destino == estado["agente"] or destino not in self.agentes:
            evento("traspaso.rechazado", logging.WARNING, destino=destino, hechos=hechos)
            texto = "Traspaso rechazado. Resuelve tú con tus herramientas o explícale al usuario lo que no puedes hacer."
            return {"historial": [{"role": "user", "content": responder(texto, True)}]}
        evento("traspaso.ok", origen=estado["agente"], destino=destino, motivo=motivo)
        texto = f"Traspaso a '{destino}' realizado. Motivo: {motivo}. Continúa tú atendiendo al usuario."
        return {"historial": [{"role": "user", "content": responder(texto, False)}],
                "agente": destino, "traza": [destino], "traspasos": hechos + 1}

    def limite(self, estado: Estado) -> dict:
        evento("presupuesto.excedido", logging.WARNING, tokens=estado.get("tokens_usados"))
        nuevos = cerrar_historial(estado["historial"], TEXTO_CORTE, "No ejecutada: se alcanzó el presupuesto de la conversación.")
        return {"historial": nuevos, "stop_reason": "limite", "respuesta": TEXTO_CORTE}

    def decidir(self, estado: Estado) -> str:
        if estado["stop_reason"] != "tool_use":
            return END
        if presupuesto_excedido(estado, self.settings):
            return "limite"  # va primero: `limite` responde TODOS los tool_use, incluido un traspaso
        ultimo = estado["historial"][-1]
        if hay_traspaso(ultimo):
            return "traspasar"
        if hay_que_aprobar(self.registry, ultimo):
            return "aprobar"
        return "tools"

    def _construir(self):
        g = StateGraph(Estado)
        for nombre in ("supervisor", "especialista", "aprobar", "tools", "traspasar", "limite"):
            g.add_node(nombre, getattr(self, nombre))
        g.add_edge(START, "supervisor")
        g.add_edge("supervisor", "especialista")
        g.add_conditional_edges("especialista", self.decidir,
                                {"limite": "limite", "traspasar": "traspasar", "aprobar": "aprobar", "tools": "tools", END: END})
        g.add_edge("aprobar", "tools")
        g.add_edge("tools", "especialista")
        g.add_edge("traspasar", "especialista")
        g.add_edge("limite", END)
        return g.compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------ API pública
    def _config(self, thread_id: str, recursion_limit: int | None = None) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit or self.settings.recursion_limit}

    def estado(self, thread_id: str) -> dict:
        return self.grafo.get_state(self._config(thread_id)).values

    def cerrar_hilo(self, thread_id: str) -> None:
        """Repara un hilo cortado a medias (p. ej. GraphRecursionError): sin esto el siguiente
        mensaje del hilo daría error 400 por un tool_use sin su tool_result."""
        config = self._config(thread_id)
        nuevos = cerrar_historial(self.grafo.get_state(config).values.get("historial", []), TEXTO_CORTE,
                                  "No ejecutada: la conversación se cortó antes de completarse.")
        if nuevos:
            self.grafo.update_state(config, {"historial": nuevos, "stop_reason": "limite", "respuesta": TEXTO_CORTE},
                                    as_node="limite")

    def eventos(self, thread_id: str, mensaje: str, aprobador: Aprobador | None = None,
                *, user_id: str | None = None, recursion_limit: int | None = None) -> Iterator[dict]:
        """Un mensaje del usuario dentro del hilo, como flujo de eventos:
        {"tipo": "nodo"|"progreso"|"aprobacion"|"final", ...}. El último es siempre "final"."""
        aprobador = aprobador or (lambda acciones: False)  # fail closed
        token = fijar_thread(thread_id)
        config = self._config(thread_id, recursion_limit)
        if self.memoria_usuario and user_id:
            for hecho in extraer_hechos(mensaje):
                self.memoria_usuario.guardar(user_id, hecho)
        entrada = {"mensaje": mensaje, "user_id": user_id or "",
                   "historial": [{"role": "user", "content": mensaje}]}
        try:
            while True:
                pendiente = None
                for modo, chunk in self.grafo.stream(entrada, config, stream_mode=["updates", "custom"]):
                    if modo == "custom":
                        yield {"tipo": "progreso", **chunk}
                        continue
                    for nodo, cambios in chunk.items():
                        if nodo == "__interrupt__":
                            pendiente = cambios[0].value
                        else:
                            yield {"tipo": "nodo", "nodo": nodo, "cambios": cambios}
                if pendiente is None:
                    break
                yield {"tipo": "aprobacion", "acciones": pendiente}
                entrada = Command(resume=bool(aprobador(pendiente)))
        except GraphRecursionError:
            evento("grafo.recursion_limit", logging.ERROR)
            self.cerrar_hilo(thread_id)
        finally:
            try:
                restaurar_thread(token)
            except ValueError:
                pass
        yield {"tipo": "final", "estado": self.estado(thread_id)}

    def hablar(self, thread_id: str, mensaje: str, aprobador: Aprobador | None = None, **kw) -> dict:
        """Como `eventos`, pero devuelve solo el estado final del hilo."""
        final = None
        for ev in self.eventos(thread_id, mensaje, aprobador, **kw):
            final = ev
        return final["estado"]
