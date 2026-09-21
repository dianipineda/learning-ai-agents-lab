import pytest

from agent_harness.config import Settings
from agent_harness.tools import Tool, ToolRegistry


def tool(**kw):
    esquema = {"type": "object", "properties": {"n": {"type": "integer"}, "modo": {"type": "string", "enum": ["a", "b"]}},
               "required": ["n"]}
    return Tool("t", "d", esquema, lambda **_: 1, **kw)


def test_validacion_de_esquema():
    t = tool()
    assert t.validar_args({"n": 1}) is None
    assert "obligatorio" in t.validar_args({})
    assert "tipo integer" in t.validar_args({"n": "x"})
    assert "tipo integer" in t.validar_args({"n": True})  # bool no es entero
    assert "uno de" in t.validar_args({"n": 1, "modo": "z"})
    assert "desconocido" in t.validar_args({"n": 1, "otro": 1})


def test_validacion_de_negocio_extra():
    assert tool(validar=lambda a: "mal" if a["n"] < 0 else None).validar_args({"n": -1}) == "mal"


def test_registro():
    reg = ToolRegistry([tool()])
    assert reg.nombres() == ["t"] and reg.schemas(["t"])[0]["name"] == "t"
    with pytest.raises(ValueError):
        reg.registrar(tool())
    with pytest.raises(KeyError):
        reg.schemas(["nope"])


def test_settings_from_env_y_con():
    s = Settings.from_env({"AGENT_PRESUPUESTO_TOKENS": "500", "AGENT_TIMEOUT": "5", "AGENT_CHECKPOINT_DB": "x.db"})
    assert s.presupuesto_tokens == 500 and s.timeout == 5.0 and s.checkpoint_db == "x.db"
    assert Settings.from_env({}).modelo == "claude-sonnet-5"
    assert s.con(max_traspasos=0).max_traspasos == 0 and s.max_traspasos == 2
