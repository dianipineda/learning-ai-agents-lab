import pytest

from agent_harness.app import crear_app
from agent_harness.config import Settings
from agent_harness.testing import FakeLLM


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def app(settings, llm):
    return crear_app(settings, llm)


def hablar(app, mensaje, aprobar=True, thread="t1", **kw):
    return app.orquestador.hablar(thread, mensaje, lambda acciones: aprobar, **kw)
