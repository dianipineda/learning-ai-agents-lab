# agent_harness — base para agentes autónomos

Plantilla para arrancar un agente (o varios) sobre la API de Anthropic + LangGraph, con el *harness*
alrededor: lo que hace que un agente sea seguro, barato y observable, no solo que "responda".

Destila las fases 7 a 11 del laboratorio (`../ejercicios`, `../soluciones`). Ejemplo incluido: soporte de pedidos.

```bash
python -m pytest -q                      # 48 pruebas, sin API
python -m agent_harness.evals --fake     # eval completo con un LLM de mentira (exit 0/1)
python -m agent_harness.evals            # eval REAL contra la API (cuesta tokens)
python -m agent_harness                  # chat de consola (necesita .env)
```
Dependencias: `pip install -e ".[dev]"` (o las de `pyproject.toml`). `.env`: `ANTHROPIC_API_KEY` y `ANTHROPIC_WORKSPACE_ID` (ver `.env.example`).

> **Estado:** verificado con `FakeLLM` (fontanería: rutas, aprobación, traspasos, hilos, límites). **No se ha corrido contra
> la API real**: antes de confiar en él, ejecuta `python -m agent_harness.evals` y ajusta `presupuesto_tokens`, prompts y umbral.

## Arquitectura

```
agent_harness/
  config.py        Settings inmutable desde el entorno (12-factor). Las fallas se inyectan con settings.con(...)
  llm.py           ÚNICO contacto con la API. Protocol LLM → se sustituye por un doble o por otro proveedor
  state.py         Estado del grafo + política por campo (acumular vs reiniciar por turno)
  graph.py         Orquestador: supervisor + especialistas + traspasos + aprobación + límite. hablar()/eventos()
  tools/           Tool (schema + política: sensible, validar, clave_idempotencia) y ToolRegistry
    soporte.py     ← tools de EJEMPLO
  agents/          AgentSpec (nombre, descripción, prompt, tools)
    soporte.py     ← agentes de EJEMPLO
  harness/
    runner.py      ÚNICA puerta de ejecución de tools: valida → aprueba → idempotencia → breaker → métricas → sobre de datos
    guardrails.py  presupuesto, traspaso, aprobación (código, no prompts)
    safety.py      idempotencia, circuit breaker, métricas, sanitización anti prompt-injection
    window.py      ventana deslizante segura (corta solo en fronteras de turno)
    repair.py      cerrar historiales rotos (tool_use sin tool_result)
  memory/          checkpointer (memoria por hilo: ':memory:' o SQLite) y memoria de largo plazo por usuario
  observability.py logs JSON por evento con thread_id
  evals/           casos + runner con puerta de calidad (guardrails ∧ todas las pasadas ≥ umbral)
  testing.py       FakeLLM (estricto: simula el error 400 si el historial es inválido)
  app.py           raíz de composición: aquí se ensamblan las piezas concretas
tests/
```

### Decisiones que importan
- **El modelo propone, el código dispone.** Aprobación humana, validación de argumentos, presupuesto y traspasos son código
  determinista. Nada crítico depende de que el modelo obedezca un prompt.
- **Fail closed.** Sin aprobador → se rechaza. La aprobación vale un solo turno (el supervisor la reinicia).
- **Un `tool_use` siempre recibe su `tool_result`,** incluso si la tool falla, se rechaza, se corta o hay traspaso. Si no, el
  siguiente mensaje del hilo da error 400. `ToolRunner` nunca lanza; `cerrar_hilo` repara hilos cortados.
- **Orden en `decidir`:** presupuesto → traspaso → aprobación → tools. El presupuesto va primero porque `limite` responde todos los `tool_use`.
- **Estado por campo:** acumulan `historial`, `traza`, `tokens_usados`; se reinician por turno `traspasos` y `aprobado`.
- **El hilo guarda todo; el modelo recibe una ventana** (`ventana_mensajes`), cortada solo en fronteras de turno.
- **Los resultados de tools son datos no confiables:** van en `<resultado_tool>`, acotados y con advertencia si parecen órdenes.
  La defensa real es la aprobación humana de las acciones sensibles.
- **Degradar, no caerse:** si la API falla, el supervisor sigue con el agente previo y el especialista responde un texto de falla
  (con el historial bien cerrado). Si una tool falla, se abre un circuit breaker.
- **Empezar simple, crecer sin reescribir:** con UN `AgentSpec` no hay llamada de supervisor ni `transferir_a`; agregar agentes = agregar specs.

## Cómo usarlo para tu proyecto
1. **Copia** esta carpeta como base de tu repo (o referencia `@plantilla/` desde Claude Code).
2. **Tools** (`tools/`): una `Tool` por capacidad. Marca `sensible=True` si tiene efectos reales, `clave_idempotencia` si un reintento
   no debe repetirla, y `validar` para las reglas de negocio. Regístralas en un `ToolRegistry`.
3. **Agentes** (`agents/`): un `AgentSpec` por especialista (`description` es lo que lee el supervisor para enrutar).
   Empieza con uno solo.
4. **Composición** (`app.py`): cambia `crear_tools_soporte`/`AGENTES_SOPORTE` por los tuyos.
5. **Evals** (`evals/casos.py`): reescribe los casos para tu dominio ANTES de tocar prompts. Es tu red de seguridad.
6. **Producción:** `AGENT_CHECKPOINT_DB=ruta.db` para memoria que sobreviva reinicios (para varias instancias, un checkpointer de
   Postgres/Redis en `memory/checkpointer.py`), `AGENT_LOG_LEVEL=INFO`, y `orq.runner.metricas.resumen()` para latencia/fallos por tool.

### Agregar un agente
```python
from agent_harness import AgentSpec
ENVIOS = AgentSpec("envios", "cambios de dirección y tiempos de entrega", "Eres el agente de ENVÍOS…", ("consultar_estado_pedido",))
# → añádelo a la lista de agentes en app.py. El supervisor y transferir_a lo incluyen solos.
```

## Fuera de alcance (a propósito)
API REST/colas/dashboard, sandboxes de código, memoria vectorial y paralelismo. Son capas que se ponen ENCIMA de esta base.
Un `Orquestador` es una librería: `hablar()` y `eventos()` se pueden exponer desde FastAPI/WebSockets sin cambiar el núcleo.
