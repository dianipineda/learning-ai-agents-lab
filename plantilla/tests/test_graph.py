import pytest

from agent_harness.agents import AgentSpec
from agent_harness.app import crear_app
from agent_harness.config import Settings
from agent_harness.graph import Orquestador
from agent_harness.harness.window import validar_historial
from agent_harness.testing import FakeLLM
from agent_harness.textos import TEXTO_CORTE, TEXTO_FALLA
from agent_harness.tools.soporte import crear_tools_soporte
from conftest import hablar


def test_consulta_simple(app):
    e = hablar(app, "¿Cómo va mi pedido RP-1001?")
    assert e["traza"] == ["pedidos"] and "en camino" in e["respuesta"] and not app.backend.reclamos


def test_queja_aprobada_crea_un_reclamo(app):
    e = hablar(app, "Mi pedido RP-1002 llegó frío y quiero un reclamo", aprobar=True)
    assert len(app.backend.reclamos) == 1 and "REC-0001" in e["respuesta"] and validar_historial(e["historial"])


def test_queja_rechazada_no_crea_nada(app):
    e = hablar(app, "Mi pedido RP-1002 llegó frío y quiero un reclamo", aprobar=False)
    assert not app.backend.reclamos and validar_historial(e["historial"])


def test_sin_aprobador_es_fail_closed(app):
    app.orquestador.hablar("t", "Mi pedido RP-1002 llegó frío y quiero un reclamo")
    assert not app.backend.reclamos


def test_traspaso_pagos_a_reclamos(app):
    e = hablar(app, "Me cobraron dos veces el pedido RP-1001 y quiero un reclamo")
    assert e["traza"] == ["pagos", "reclamos"] and len(app.backend.reclamos) == 1 and validar_historial(e["historial"])


def test_traspaso_rechazado_por_limite(llm):
    app = crear_app(Settings(max_traspasos=0), llm)
    e = hablar(app, "Me cobraron dos veces el pedido RP-1001 y quiero un reclamo")
    assert e["traza"] == ["pagos"] and not app.backend.reclamos and validar_historial(e["historial"])


def test_tool_caida_no_tumba_el_grafo(app):
    e = hablar(app, "¿Cómo va mi pedido RP-9999?")
    assert "problema técnico" in e["respuesta"] and validar_historial(e["historial"])


def test_api_caida_degrada_y_el_hilo_sigue_vivo(settings):
    llm = FakeLLM(falla=True)
    app = crear_app(settings, llm)
    e = hablar(app, "¿Cómo va mi pedido RP-1001?")
    assert e["stop_reason"] == "error" and e["respuesta"] == TEXTO_FALLA and validar_historial(e["historial"])
    llm.falla = False  # la API vuelve: el MISMO hilo responde (FakeLLM estricto simula el 400)
    assert "en camino" in hablar(app, "¿Y ahora? RP-1001")["respuesta"]


def test_presupuesto_agotado_corta_con_historial_valido(llm):
    app = crear_app(Settings(presupuesto_tokens=1), llm)
    e = hablar(app, "Mi pedido RP-1002 llegó frío y quiero un reclamo")
    assert e["stop_reason"] == "limite" and e["respuesta"] == TEXTO_CORTE
    assert not app.backend.reclamos and validar_historial(e["historial"])


def test_memoria_por_hilo_entre_turnos(app):
    hablar(app, "Mi pedido llegó frío y quiero registrar un reclamo")
    e = hablar(app, "Es el RP-1002")
    assert e["traza"] == ["reclamos", "reclamos"] and len(app.backend.reclamos) == 1


def test_hilos_distintos_no_comparten_memoria(app):
    hablar(app, "Mi pedido llegó frío y quiero registrar un reclamo", thread="a")
    e = hablar(app, "Es el RP-1002", thread="b")
    assert e["traza"] == ["pedidos"] and not app.backend.reclamos


def test_aprobado_se_reinicia_por_turno(app):
    hablar(app, "Mi pedido RP-1002 llegó frío y quiero un reclamo", aprobar=True)
    e = hablar(app, "Mi pedido RP-1003 llegó incompleto y quiero un reclamo", aprobar=False)  # otro turno, otro permiso
    assert len(app.backend.reclamos) == 1 and validar_historial(e["historial"])


def test_hilo_cortado_por_recursion_se_repara(app):
    e = hablar(app, "Mi pedido RP-1002 llegó frío y quiero un reclamo", recursion_limit=3)
    assert e["stop_reason"] == "limite" and validar_historial(e["historial"])
    e2 = hablar(app, "¿Cómo va mi pedido RP-1001?")  # el FakeLLM estricto lanzaría el 400 si quedara roto
    assert "en camino" in e2["respuesta"]


def test_ventana_limita_lo_que_se_envia_pero_no_lo_que_se_guarda(llm):
    app = crear_app(Settings(ventana_mensajes=4), llm)
    for i in range(6):
        hablar(app, f"¿Cómo va mi pedido RP-100{i % 3 + 1}?")
    enviados = [len(c["messages"]) for c in llm.llamadas if c["tool_choice"] is None]
    assert max(enviados) <= 4 and len(app.orquestador.estado("t1")["historial"]) > 4
    assert all(validar_historial(c["messages"]) for c in llm.llamadas if c["tool_choice"] is None)


def test_un_solo_agente_no_usa_supervisor_ni_transferir(settings):
    llm = FakeLLM()
    solo = AgentSpec("pedidos", "todo", "Eres el agente de PEDIDOS.", ("consultar_estado_pedido",))
    orq = Orquestador(settings, llm, crear_tools_soporte(), [solo])
    e = orq.hablar("t", "¿Cómo va mi pedido RP-1001?")
    assert e["traza"] == ["pedidos"] and all(c["tool_choice"] is None for c in llm.llamadas)
    assert all("transferir_a" not in [t["name"] for t in c["tools"]] for c in llm.llamadas)


def test_agente_con_tool_no_registrada_falla_al_construir(settings, llm):
    with pytest.raises(KeyError):
        Orquestador(settings, llm, crear_tools_soporte(), [AgentSpec("x", "d", "s", ("no_existe",))])


def test_eventos_orden_y_aprobacion(app):
    evs = list(app.orquestador.eventos("t", "Mi pedido RP-1002 llegó frío y quiero un reclamo", lambda a: True))
    tipos = [e["tipo"] for e in evs]
    assert tipos[-1] == "final" and "aprobacion" in tipos
    nodos = [e["nodo"] for e in evs if e["tipo"] == "nodo"]
    assert nodos[0] == "supervisor" and "aprobar" in nodos and nodos[nodos.index("aprobar") + 1] == "tools"
    assert [e["tool"] for e in evs if e["tipo"] == "progreso"] == ["consultar_estado_pedido", "crear_reclamo"]


def test_la_aprobacion_de_un_turno_no_sobrevive_al_siguiente(app):
    assert hablar(app, "Mi pedido RP-1002 llegó frío y quiero un reclamo", aprobar=True)["aprobado"] is True
    assert hablar(app, "¿Cómo va mi pedido RP-1001?")["aprobado"] is False  # el supervisor lo reinicia (fail closed)
