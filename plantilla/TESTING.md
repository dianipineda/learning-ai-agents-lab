# Guía de testing — agent_harness

Cómo probar el harness sin gastar tokens, cuándo sí gastarlos, y cómo agregar un test nuevo.
Ver también [`TOUR.md`](TOUR.md) para el porqué de la arquitectura.

## La filosofía

La plantilla separa **dos preguntas distintas** que un agente necesita responder, y usa una
herramienta distinta para cada una:

| Pregunta | Herramienta | Qué verifica | Costo |
| --- | --- | --- | --- |
| ¿La fontanería funciona? (rutas, aprobación, traspasos, límites, hilos) | `pytest` + `FakeLLM` | Lógica determinista del harness | Gratis, rápido |
| ¿El agente responde bien de verdad? | `agent_harness.evals` | Calidad de las respuestas del LLM real | Sí, cuesta tokens |

**`FakeLLM`** (`agent_harness/testing.py`) es la pieza que hace esto posible: es un doble de prueba que
*no entiende lenguaje*, aplica reglas simples según qué tools ve el agente (por ejemplo: si el mensaje
trae un número de pedido `RP-####` y las tools incluyen `crear_reclamo`, simula el flujo de un
reclamo). Tiene un modo `estricto=True` que **simula el error 400 real de la API**
(`harness/window.py::validar_historial`) si el historial que le llega está mal formado — así un test
detecta un historial roto sin gastar un solo token.

Las fallas (API caída, presupuesto agotado) se **inyectan por construcción** (`FakeLLM(falla=True)`,
`Settings.con(presupuesto_tokens=1)`), nunca con `monkeypatch`. Es una regla explícita en
`plantilla/CLAUDE.md`.

Los evals (`agent_harness/evals/runner.py`) tienen dos partes:

- **A. Guardrails** (`pruebas_guardrails`): sin modelo, código puro (validación de argumentos, qué
  tools son sensibles). Deben pasar siempre.
- **B. Casos de punta a punta** (`agent_harness/evals/casos.py`): conversaciones completas, repetidas
  3 veces por defecto. Como el LLM no es determinista, se exige que **todas** las pasadas superen el
  umbral (80% por defecto) — se busca estabilidad, no una corrida con suerte.

El eval termina con un veredicto explícito: `LISTO PARA PRODUCCIÓN` o `NO LISTO`, según si los
guardrails pasaron y todas las pasadas superaron el umbral.

## Cómo correr los tests

Siempre desde `plantilla/`:

| Comando | Qué hace | Gasta tokens |
| --- | --- | --- |
| `python -m pytest -q` | Corre las 48 pruebas unitarias (`tests/`). Fontanería pura con `FakeLLM` | No |
| `python -m agent_harness.evals --fake` | Eval completo (guardrails + casos de punta a punta) contra `FakeLLM`. Sale con código 0/1 | No |
| `python -m agent_harness.evals` | El mismo eval, pero contra la API real de Anthropic | Sí |

**Flujo recomendado al cambiar algo:**

1. `python -m pytest -q` — tiene que quedar en verde.
2. `python -m agent_harness.evals --fake` — tiene que salir con exit 0.
3. `python -m agent_harness.evals` (real) — correrlo varias veces y confirmar que supera el umbral de
   forma **estable**, no solo una vez.

Esto está escrito explícitamente como regla en `plantilla/CLAUDE.md`, bajo "Antes de dar algo por
hecho". También ahí: **un cambio en un guardrail o en el orden de `decidir` necesita una prueba que
falle sin él** — si tocaste algo de seguridad, el test tiene que demostrar que sin tu cambio, se rompe.

## Cómo escribir un test nuevo

### Patrón 1: test unitario de harness (`tests/`)

Usa los fixtures de `tests/conftest.py`: `settings`, `llm` (un `FakeLLM()`) y `app` (armado con
`crear_app`). El helper `hablar(app, mensaje, aprobar=True, thread="t1")` manda un mensaje y devuelve
el estado final.

```python
def test_pedido_se_consulta(app):
    estado = hablar(app, "¿Cómo va mi pedido RP-1001?")
    assert estado["traza"][0] == "pedidos"
    assert "RP-1001" in estado["respuesta"]
```

Para probar guardrails o piezas de `harness/` en aislamiento (como `tests/test_safety.py`), no hace
falta el `app` completo — se instancia la pieza directo:

```python
def test_breaker_abre_tras_3_fallos():
    cb = CircuitBreaker(3, 30.0, reloj)
    for _ in range(3):
        cb.fallo()
    assert not cb.permitir()
```

Para inyectar una falla (API caída, historial roto), se construye el doble con esa falla — nunca
`monkeypatch`:

```python
def test_llm_caido_degrada_con_texto_de_falla(settings):
    app = crear_app(settings, FakeLLM(falla=True))
    estado = hablar(app, "¿Cómo va mi pedido RP-1001?")
    assert estado["stop_reason"] == "error"
```

### Patrón 2: caso de eval de punta a punta (`evals/casos.py`)

Es un diccionario, no código. Se agrega a la lista `CASOS` y el `runner.py` ya sabe interpretarlo:

```python
{
    "nombre": "consulta de pedido inexistente",
    "mensajes": ["¿Cómo va mi pedido RP-9999?"],
    "agente": "pedidos",                    # primer agente que debe atender
    "tools": {"consultar_estado_pedido"},   # tools de negocio que deben intentarse
    "reclamos": 0,                          # reclamos que deben quedar CREADOS de verdad
    "responde_con": "problema técnico",     # texto esperado en la respuesta final
}
```

Campos opcionales útiles: `termina_en` (si hay traspaso), `aprobar` (qué decide el humano simulado),
`stop_reason`, `presupuesto` / `falla_api` (para inyectar fallas en ese caso puntual).

### Regla de oro al agregar cualquiera de los dos

Si el test es sobre un guardrail o el orden de `decidir()` en `graph.py`, primero verificá que el test
**falle** si comentás temporalmente el guardrail — si no falla, el test no está probando lo que creés.
