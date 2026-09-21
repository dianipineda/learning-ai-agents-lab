from agent_harness.app import crear_app
from agent_harness.config import Settings
from agent_harness.evals.runner import evaluar, evaluar_caso, pruebas_guardrails
from agent_harness.evals.casos import CASOS
from agent_harness.testing import FakeLLM


def test_guardrails(settings):
    assert pruebas_guardrails(crear_app(settings, FakeLLM()))


def test_eval_completo_con_fake_pasa(capsys):
    assert evaluar(crear_app, Settings(), FakeLLM(), repeticiones=2, umbral=0.8)


def test_el_eval_detecta_una_ruta_mala():
    caso = dict(CASOS[0], agente="pagos")  # esperamos un agente que no corresponde
    assert not evaluar_caso(caso, crear_app, Settings(), FakeLLM())
