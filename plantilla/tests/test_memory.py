from agent_harness.app import crear_app
from agent_harness.config import Settings
from agent_harness.memory.checkpointer import crear_checkpointer
from agent_harness.memory.usuario import MemoriaUsuario, extraer_hechos
from agent_harness.testing import FakeLLM
from conftest import hablar


def test_memoria_usuario_reglas():
    t = [0.0]
    m = MemoriaUsuario(ttl_segundos=100, reloj=lambda: t[0])
    assert m.guardar("ana", "Se llama Ana") and not m.guardar("ana", "se llama ana")
    assert not m.guardar("ana", "Mi tarjeta es 4111 1111 1111 1111") and not m.guardar("ana", "  ")
    m.guardar("beto", "Vive en Bogotá")
    assert m.recordar("ana") == ["Se llama Ana"] and m.recordar("beto") == ["Vive en Bogotá"] and m.recordar("zoe") == []
    t[0] = 101
    assert m.recordar("ana") == []  # TTL


def test_extraer_hechos():
    assert extraer_hechos("Hola, me llamo Ana y vivo en Cali.") == ["Se llama Ana", "Vive en Cali"]
    assert extraer_hechos("¿dónde está mi pedido?") == []


def test_memoria_de_largo_plazo_llega_al_prompt_solo_del_usuario(settings):
    llm = FakeLLM()
    app = crear_app(settings, llm)
    hablar(app, "Hola, me llamo Ana. ¿Cómo va mi pedido RP-1001?", thread="a", user_id="ana")
    hablar(app, "¿Cómo va mi pedido RP-1001?", thread="otro-hilo", user_id="ana")  # hilo NUEVO, mismo usuario
    hablar(app, "¿Cómo va mi pedido RP-1001?", thread="c", user_id="beto")
    sistemas = [c["system"] for c in llm.llamadas if c["tool_choice"] is None]
    assert "Se llama Ana" in sistemas[-4]  # el turno del hilo nuevo de ana
    assert "Se llama Ana" not in sistemas[-1]  # beto no ve lo de ana


def test_sqlite_sobrevive_al_reinicio(tmp_path):
    ruta = str(tmp_path / "cp.db")
    s = Settings(checkpoint_db=ruta)
    a1 = crear_app(s, FakeLLM(), crear_checkpointer(ruta))
    hablar(a1, "Mi pedido llegó frío y quiero registrar un reclamo", thread="persistente")  # pide el número
    a2 = crear_app(s, FakeLLM(), crear_checkpointer(ruta))  # "reinicio": otra app, mismo archivo
    e = hablar(a2, "Es el RP-1002", thread="persistente")
    assert e["traza"] == ["reclamos", "reclamos"] and len(a2.backend.reclamos) == 1
