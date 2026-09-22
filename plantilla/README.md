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

## Detalle de archivos y carpetas

La tabla de arriba es el mapa; esto es el porqué de cada pieza: qué problema resuelve, por qué existe
separada de las demás y qué pasa si no estuviera. Para el "por qué" de las decisiones de diseño en
conjunto, ver [`TOUR.md`](TOUR.md); para cómo probar cada pieza, [`TESTING.md`](TESTING.md).

### Raíz del repo

- **`README.md`** — este archivo: qué es la plantilla, cómo correrla, mapa de arquitectura y cómo
  adaptarla a un proyecto propio. Es lo primero que se lee.
- **`CLAUDE.md`** — instrucciones para el asistente (Claude Code) cuando trabaja *sobre* esta carpeta:
  las reglas invariantes ("toda tool pasa por `ToolRunner`", "guardrails = código, no prompts") para que
  un cambio no las rompa sin darse cuenta. No es documentación para humanos, es contexto de agente.
- **`TOUR.md`** — recorrido didáctico de la arquitectura: el problema que resuelve el harness, el flujo
  del grafo explicado con más calma que el README, y el porqué de cada decisión de diseño. Está para
  quien llega sin haber hecho las fases 7-11 del laboratorio y necesita el contexto completo antes de
  tocar código.
- **`TESTING.md`** — guía de testing: qué verifica `pytest`+`FakeLLM` (fontanería, gratis) vs. qué
  verifica `agent_harness.evals` (calidad real, cuesta tokens), cómo escribir un test nuevo o un caso de
  eval nuevo, y la regla de oro de probar que un guardrail realmente falla si se lo comenta.
- **`pyproject.toml`** — metadata del paquete (`agent-harness`) y sus dependencias (`anthropic`,
  `langgraph`, `langgraph-checkpoint-sqlite`, `python-dotenv`; `pytest` como dependencia opcional
  `[dev]`). También configura `pytest` (`testpaths = ["tests"]`) y qué paquetes empaqueta
  `setuptools`. Es lo que hace posible `pip install -e ".[dev]"`.
- **`.env.example`** — plantilla de las variables de entorno que lee `config.py` (`ANTHROPIC_API_KEY`,
  `ANTHROPIC_WORKSPACE_ID` y las opcionales `AGENT_*`). Se copia a `.env` (que `.gitignore` excluye) para
  no commitear secretos ni configuración local.
- **`.gitignore`** — excluye `.env` (secretos), `__pycache__/` y `.pytest_cache/` (basura de ejecución),
  `*.db` (el SQLite de `AGENT_CHECKPOINT_DB`, que es estado local, no código) y `*.egg-info/` (metadata
  generada por la instalación editable).
- **`tests/`** — la suite de `pytest` (48 pruebas). No importa nada de `anthropic`: usa `FakeLLM`
  (`agent_harness/testing.py`) para verificar la fontanería del harness sin gastar tokens ni depender de
  la red. Un archivo por área: `test_graph.py` (el grafo y sus rutas), `test_runner.py` (`ToolRunner`),
  `test_safety.py` (idempotencia, circuit breaker, sanitización), `test_window.py` (ventana y validación
  de historial), `test_memory.py` (checkpointer y memoria de usuario), `test_tools_config.py` (`Tool` y
  `ToolRegistry`), `test_evals.py` (que el propio runner de evals funcione) y `conftest.py` (fixtures
  compartidas: `settings`, `llm`, `app`, el helper `hablar(...)`).

### `agent_harness/` — el paquete

- **`__init__.py`** — la API pública del paquete: qué símbolos se exponen con
  `from agent_harness import ...` (`AgentSpec`, `Orquestador`, `Settings`, `Tool`, `ToolRegistry`). Marca
  qué es "interfaz estable" del harness frente a lo que es detalle interno.
- **`__main__.py`** — el chat de consola (`python -m agent_harness`). Es una integración de referencia,
  no el producto: arma la app con `crear_app`, mantiene un `thread_id` por sesión ("nuevo" abre otro), y
  resuelve las aprobaciones humanas con un simple `input()`. Sirve para probar el agente a mano contra la
  API real.
- **`config.py`** — `Settings`, un `dataclass` **inmutable** con cada número que el harness necesita
  ajustar (presupuesto de tokens, tamaño de ventana, umbral del circuit breaker, etc.), leído del entorno
  al estilo 12-factor (`Settings.from_env()`). Es inmutable a propósito: para simular una falla o un
  límite distinto en un test o un eval se usa `settings.con(presupuesto_tokens=1)`, que devuelve una
  copia — nunca se muta configuración compartida ni se usa `monkeypatch`.
- **`llm.py`** — el **único** archivo que importa `anthropic`. Define el `Protocol LLM` (un `.crear(...)`
  que devuelve `Respuesta`) del que depende todo el resto del harness, y `AnthropicLLM`, la única
  implementación real. Existe separado para que se pueda sustituir por `testing.py::FakeLLM` en tests y
  evals sin tocar `graph.py`, y para que cambiar de proveedor (u otro modelo) sea aislado a este archivo.
- **`state.py`** — `Estado`, el `TypedDict` que viaja por el grafo de LangGraph. Como hay memoria por
  hilo, cada campo necesita una política explícita de qué hacer entre turnos: `historial`, `traza` y
  `tokens_usados` **acumulan** (`Annotated[..., operator.add]`); `traspasos` y `aprobado` se
  **reinician** cada turno (así una aprobación nunca "sobra" para el turno siguiente — ver guardrails);
  el resto se sobreescribe. Es el archivo a mirar antes de agregar un campo nuevo al estado.
- **`graph.py`** — `Orquestador`: arma el `StateGraph` (supervisor → especialista → nodos de harness) y
  expone la API pública (`hablar()`, `eventos()`). Es el archivo más grande a propósito: es donde se
  conectan config, llm, tools, agentes, harness y memoria. El orden de las ramas en `decidir()`
  (presupuesto → traspaso → aprobación → tools) es una decisión de seguridad documentada ahí mismo, no
  un detalle de implementación.
- **`app.py`** — la **raíz de composición**: el único lugar que decide qué implementaciones concretas se
  usan (`AnthropicLLM`, `SoporteBackend`, `AGENTES_SOPORTE`...). Separarlo de `graph.py` es lo que
  permite que `Orquestador` no sepa nada del dominio de soporte de pedidos: para adaptar la plantilla a
  otro proyecto, este es el archivo que se reescribe (junto con `tools/` y `agents/`).
- **`observability.py`** — logging estructurado: una línea JSON por evento (`evento("tool.ok", ...)`),
  correlacionada por `thread_id` vía `contextvars` (para poder seguir una conversación en logs
  concurrentes). Como es una librería, arranca en silencio (`NullHandler`) hasta que algo llama
  `configurar_logging(...)` — así no le impone su formato de logs a quien la use.
- **`testing.py`** — `FakeLLM`: un doble de prueba que **no entiende lenguaje**, solo aplica reglas
  simples según qué tools ve el agente. Existe para que `tests/` y `evals --fake` puedan correr toda la
  fontanería del harness (rutas, aprobación, traspasos, límites) sin gastar tokens ni depender de la
  red. Su modo `estricto=True` simula el error 400 real de la API si el historial que recibe está mal
  formado, así un test detecta un historial roto sin tocar la API.
- **`textos.py`** — los dos textos que el harness le muestra al usuario cuando algo sale mal
  (`TEXTO_FALLA` si la API falla, `TEXTO_CORTE` si se corta por presupuesto). Están separados en su
  propio archivo porque son texto de producto en español, no lógica: cambiarlos no debería requerir
  tocar `graph.py`.

### `agent_harness/tools/` — qué puede *hacer* un agente

- **`base.py`** — el contrato `Tool`: un `dataclass` con el `schema` que se le manda a la API
  (`name`, `description`, `input_schema`) y la **política** de cómo tratarla (`sensible` → exige
  aprobación humana, `validar` → reglas de negocio sobre los argumentos, `clave_idempotencia` → un
  reintento no la repite). También valida tipos/`enum`/requeridos contra el `input_schema` antes de
  llegar a `validar`. Es el archivo a mirar para entender qué puede declarar una tool.
- **`registry.py`** — `ToolRegistry`: el catálogo de tools registradas por nombre. Un `AgentSpec` solo
  guarda *nombres* de tools (strings); el registro es lo que los resuelve a la `Tool` real y genera los
  schemas que se envían a la API. Registrar dos tools con el mismo nombre falla explícito (no se pisan
  en silencio).
- **`soporte.py`** — las tools de **ejemplo** (soporte de pedidos de Rappi, con datos simulados en
  memoria). Muestra las tres clases de tool que hay que saber escribir: de solo consulta
  (`consultar_estado_pedido`), una que puede fallar para probar resiliencia (`RP-9999` simula un backend
  caído) y una con efectos reales (`crear_reclamo`: `sensible=True` + `clave_idempotencia`). Se reemplaza
  por completo al adaptar la plantilla a otro dominio.
- **`__init__.py`** — reexporta `Tool` y `ToolRegistry` para poder hacer `from agent_harness.tools import
  Tool, ToolRegistry` sin conocer en qué archivo interno viven.

### `agent_harness/agents/` — quién responde

- **`base.py`** — `AgentSpec` (nombre, `description` — lo que lee el **supervisor** para decidir a quién
  enrutar —, prompt de sistema y tupla de nombres de tools) y `prompt_supervisor(...)`, que arma el
  prompt del supervisor a partir de la lista de `AgentSpec`. Agregar un agente nuevo es escribir un
  `AgentSpec` más; el grafo (`graph.py`) no se toca.
- **`soporte.py`** — los agentes de **ejemplo**: `PEDIDOS`, `RECLAMOS` y `PAGOS`, con sus prompts en
  español y las reglas comunes (no inventar datos, no insistir si una tool falla). Muestra cómo un
  prompt le indica a un agente cuándo usar `transferir_a(...)` hacia otro. Se reemplaza junto con
  `tools/soporte.py` y `app.py` al cambiar de dominio.
- **`__init__.py`** — reexporta `AgentSpec` y `prompt_supervisor`.

### `agent_harness/harness/` — las reglas de seguridad, como código

Esta carpeta es la respuesta a "el modelo propone, el código dispone": nada de lo que hay aquí depende
de que un prompt se obedezca.

- **`runner.py`** — `ToolRunner`, la **única puerta** por la que se ejecuta una tool. Aplica en orden:
  tool conocida → argumentos válidos → aprobación humana (si es sensible) → idempotencia → circuit
  breaker → métricas → resultado envuelto como datos no confiables. Nunca lanza una excepción hacia
  afuera: siempre devuelve un `tool_result`, porque un `tool_use` sin su `tool_result` deja el historial
  roto (error 400 en el siguiente turno). Existe separado de `graph.py` para poder probarlo (y
  reutilizarlo) sin levantar el grafo completo.
- **`guardrails.py`** — las decisiones de negocio que **no** pueden depender del modelo: si hay
  traspaso (`hay_traspaso`), si se excedió el presupuesto de tokens (`presupuesto_excedido`), si una
  tool necesita aprobación humana (`requiere_aprobacion` — solo si es sensible *y* sus argumentos ya son
  válidos, para no molestar a un humano con una llamada que se iba a rechazar igual). `graph.py::decidir`
  es literalmente estas funciones en el orden correcto.
- **`safety.py`** — seguridad **operativa** de las tools, cuatro piezas independientes:
  `EjecutorIdempotente` (misma clave = se ejecuta una sola vez; solo recuerda lo que salió bien, para no
  bloquear un reintento tras un fallo), `CircuitBreaker` (tras N fallos seguidos deja de intentar por un
  tiempo), `Metricas` (latencia y tasa de fallo por tool, para `runner.metricas.resumen()`) y
  `sanitizar`/`es_sospechoso` (los resultados de tools son datos no confiables: se envuelven en
  `<resultado_tool>`, se acotan en tamaño y se marca si el texto parece un intento de prompt injection).
- **`window.py`** — la ventana deslizante: el hilo completo se guarda en el checkpointer, pero al modelo
  solo se le envían los últimos `ventana_mensajes`. Cortar a ciegas (`historial[-n:]`) puede dejar un
  `tool_result` sin su `tool_use` o un historial que no arranca en `user`; por eso `recortar_historial`
  solo corta en **fronteras de turno**. `validar_historial` es la misma regla en modo verificación, y es
  lo que `FakeLLM` usa para simular el error 400 sin tocar la API real.
- **`repair.py`** — qué agregar al historial para dejarlo bien formado y cerrado cuando algo lo corta a
  medias (se agotó el presupuesto, `GraphRecursionError`): un `tool_result` de error por cada `tool_use`
  pendiente, más un mensaje de cierre. Lo usan tanto `graph.py::limite` (corte por presupuesto) como
  `graph.py::cerrar_hilo` (reparar un hilo que quedó a medias tras un `GraphRecursionError`).
- **`__init__.py`** — vacío; la carpeta es un paquete, no reexporta nada (cada módulo se importa por su
  nombre porque cada uno es una responsabilidad distinta).

### `agent_harness/memory/` — lo que se recuerda

- **`checkpointer.py`** — la memoria **por hilo** (la conversación completa, tal como la usa
  LangGraph): `crear_checkpointer(ruta)` devuelve un `MemorySaver` (volátil, para dev/tests) si
  `ruta == ":memory:"` o un `SqliteSaver` si se le da una ruta de archivo (persiste entre reinicios,
  vía `AGENT_CHECKPOINT_DB`). Aislar esto en una función es lo que permite cambiarlo por un checkpointer
  de Postgres/Redis (para escalar horizontalmente) sin que el resto del harness se entere.
- **`usuario.py`** — `MemoriaUsuario`: memoria de **largo plazo** por `user_id`, fuera del hilo (por
  ejemplo, "vive en Bogotá" debería recordarse aunque el usuario abra una conversación nueva). Sencilla
  a propósito (sin embeddings ni vector store: con pocos hechos por usuario alcanza con guardar los más
  recientes), con TTL y con un filtro (`SENSIBLE`) que evita guardar algo que parezca un número de
  tarjeta o cuenta. `extraer_hechos(...)` son los patrones de ejemplo que detectan un hecho nuevo en el
  mensaje del usuario.
- **`__init__.py`** — vacío, igual que en `harness/`.

### `agent_harness/evals/` — la red de seguridad antes de tocar prompts

- **`casos.py`** — `CASOS`: la lista de conversaciones de punta a punta que definen "el agente responde
  bien" para el dominio de ejemplo (soporte de pedidos). Cada caso es un diccionario declarativo (no
  código): qué mensajes manda el usuario, qué agente debe atenderlos, qué tools deben intentarse, cuántos
  reclamos deben quedar creados de verdad, qué decide el "humano automático", y fallas a inyectar
  (`presupuesto`, `falla_api`). Es lo primero que hay que reescribir para adaptar la plantilla a otro
  dominio — **antes** de tocar los prompts de `agents/`.
- **`runner.py`** — `evaluar(...)`, con dos partes: **A. guardrails** (`pruebas_guardrails`, sin modelo,
  código puro — deben pasar siempre) y **B. casos de punta a punta** (`evaluar_caso`, repetidos varias
  veces porque el LLM no es determinista: se exige que **todas** las pasadas superen el umbral, no una
  con suerte). Termina con un veredicto explícito ("LISTO PARA PRODUCCIÓN" / "NO LISTO") y código de
  salida 0/1, para poder engancharlo a CI.
- **`__main__.py`** — el CLI `python -m agent_harness.evals [--fake] [--repeticiones N] [--umbral X]`.
  Con `--fake` usa `FakeLLM` (verifica fontanería, gratis); sin él, pega contra la API real (cuesta
  tokens, es el eval que de verdad importa antes de confiar en el agente).
- **`__init__.py`** — vacío.

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
