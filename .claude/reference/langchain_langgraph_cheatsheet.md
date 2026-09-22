# Cheat-sheet: LangChain, LangGraph y Agentes de IA

Referencia técnica de consulta rápida, condensada de un cuaderno de trabajo personal
("Curso completo de LangChain, LangGraph y Agentes de IA con Python" — S. Hernández Ramos).
No es parte del curriculum ni de `plantilla/`: es material de apoyo transversal, útil en
cualquier fase donde aparezcan estos conceptos (fases 3–11).

> Nota: son apuntes de un curso general (OpenAI/Gemini como ejemplo). En este repo el proveedor
> es siempre Anthropic — traducir `ChatOpenAI`/`llm.invoke` a la API de Anthropic o al
> `Protocol LLM` de `plantilla/agent_harness/llm.py` según corresponda.

## Tema 1 — Primeros pasos con LangChain

- Entorno: `python -m venv venv`, instalar `langchain` + el conector del proveedor.
- Interfaz unificada: `llm.invoke(prompt)` → `.content` tiene el texto, sin importar el proveedor.
- `PromptTemplate(input_variables=[...], template="...")` — plantillas reutilizables con `{var}`.
- `LLMChain` es la API clásica (deprecada); el patrón moderno es LCEL: `chain = prompt | llm`.
- Temperatura: `0.0–0.2` precisión/factual, `0.3–0.7` equilibrio, `0.8–1.0` creatividad.
- Roles de mensaje: `SystemMessage` (instrucciones, no se muestran al usuario), `HumanMessage`,
  `AIMessage`, todos heredan de `BaseMessage`.
- Streamlit para UI de chat: `st.session_state` para persistir mensajes entre reruns,
  `st.chat_message(role)` / `st.chat_input()`, `chain.stream(...)` para respuesta progresiva.

## Tema 2 — Runnables y LCEL (núcleo de las "cadenas")

- **Runnable**: cualquier objeto invocable con `.invoke(x) → output`; es la base de LCEL.
- **Pipe (`|`)**: compone Runnables en secuencia (`prompt | llm | parser`).
- **`RunnableLambda(fn)`**: adapta una función Python normal a Runnable.
- **`RunnableParallel({key: runnable, ...})`**: corre varias ramas sobre el mismo input y
  devuelve un `dict` con los resultados — útil cuando varios pasos no dependen entre sí.
- **`.batch([in1, in2, ...])`**: procesa una lista de inputs con la misma cadena; preferible a un
  loop con `.invoke` cuando hay 2+ elementos (menos overhead, mismo orden de salida).
- **Output Parsers**: `StrOutputParser`, `JsonOutputParser`, `PydanticOutputParser`,
  `CsvOutputParser` — casi toda cadena LCEL debería terminar en un parser.
- **Salidas estructuradas con Pydantic**: define un `BaseModel` con `Field(..., description=...)`
  (la descripción es lo que el LLM usa como contrato) y usa
  `chat.with_structured_output(MiModelo)` en vez de parsear texto libre a mano.
- **`ChatPromptTemplate.from_messages([...])`**: plantilla de lista de mensajes con roles
  (`"system"`, `"human"`, `"ai"`).
- **`MessagesPlaceholder(variable_name="historial")`**: inyecta una lista de mensajes ya tipados
  (no un string concatenado) dentro de un `ChatPromptTemplate` — el patrón correcto para meter
  historial de conversación.
- Estructura de proyecto sugerida: `models/` (esquemas Pydantic), `prompts/` (plantillas),
  `services/` (I/O externo), `ui/`.

## Tema 3 — RAG (Retrieval-Augmented Generation)

Pipeline de ingesta: **cargar → splittear → embeddings → indexar**.
Pipeline de consulta: **query→embedding → buscar top-k → recuperar chunks+metadata → (rerank
opcional) → pasar como contexto al LLM**.

- **Document loaders** (`langchain_community.document_loaders`): normalizan fuentes externas a
  `Document(page_content, metadata)`. Ej.: `PyPDFLoader` (1 `Document` por página),
  `WebBaseLoader`, `DirectoryLoader`.
- **Text splitters**: `RecursiveCharacterTextSplitter` es la opción por defecto ("inteligente":
  corta por párrafo → oración → palabra). Parámetros clave: `chunk_size`, `chunk_overlap`
  (10–20% del tamaño), `separators`. El overlap evita que una respuesta "pierda el hilo" en el
  borde de un corte.
- **Embeddings**: vector de longitud fija que codifica significado; textos similares → vectores
  cercanos. Regla de oro: **usar el mismo modelo de embeddings para indexar y para consultar**;
  no mezclar modelos/dimensiones en el mismo índice.
- **VectorStores** (Chroma, FAISS, Pinecone, Qdrant...): `Chroma.from_documents(docs,
  embedding_function=emb, persist_directory=...)` para crear; reabrir con
  `Chroma(persist_directory=..., embedding_function=emb)` sin reingerir.
- **Retrievers**: interfaz uniforme sobre un vectorstore —
  `vectorstore.as_retriever(search_type="similarity"|"mmr"|"similarity_score_threshold",
  search_kwargs={...})`. MMR (`max_marginal_relevance_search`) da más diversidad, menos
  duplicados.
- **Multi-Query Retriever**: usa un LLM para generar variantes de la query (sinónimos,
  subconsultas), busca con cada una y fusiona resultados — útil con queries ambiguas.
- **Ensemble Retriever**: combina varios retrievers con pesos (`weights`); bueno para
  colecciones con vocabulario heterogéneo.
- Prompt de RAG: instrucción explícita de "responde solo con el CONTEXTO; si no está, dí que no
  sabes" (grounding) + citar `source/page/chunk_id`.
- Métricas de calidad: *faithfulness/groundedness* (no alucina), *context precision/recall*.

## Tema 4 — LangGraph

- **Qué añade sobre LangChain**: grafos con ciclos, ramificación dinámica y estado global
  compartido — para flujos con decisiones, iteración o memoria persistente. Flujos lineales
  simples siguen mejor con LCEL puro.
- **Estado**: normalmente un `TypedDict`. Cada nodo **lee** el estado como dict y **devuelve un
  dict parcial**; LangGraph lo fusiona sobre el estado completo (no hace falta devolver todo).
- **Nodo**: función `(state) -> dict` o un Runnable. Mantenerlos pequeños, puros si es posible,
  de una sola responsabilidad.
- **Arista**: conexión dirigida. `add_edge(A, B)` fija flujo secuencial; hay que fijar
  `START`→primer nodo y algún nodo→`END`.
- **Patrón base**: definir estado → `StateGraph(Estado)` → `add_node(...)` por cada paso →
  `add_edge(...)` para conectarlos → `.compile()` (una vez) → `.invoke(estado_inicial)`.
- **`Annotated` + reducers**: por defecto, si dos nodos escriben la misma clave, la última
  escritura gana. Para **acumular** (logs, listas, contadores), anotar el campo como
  `Annotated[list[str], operator.add]` (o un reducer custom) — así es como `plantilla/state.py`
  acumula `historial`/`traza`/`tokens_usados`.
- **Routing / aristas condicionales**: `add_conditional_edges(source, router_fn, {clave:
  nodo_destino, ...})`. El `router_fn(state) -> str` debe ser puro (no mutar estado) y devolver
  una clave que exista en el mapeo; prever una ruta de fallback.
- **Streaming**: `app.stream(estado_inicial, config=..., stream_mode=...)` — `"updates"` (diffs
  por nodo, lo más común para UI), `"values"` (estado completo tras cada nodo, debug), `"messages"`
  (tokens/mensajes del LLM), `"debug"` (todo).
- **Threading/config**: `config={"configurable": {"thread_id": id}}` — identifica la ejecución y
  habilita reanudación contra el mismo checkpoint.
- **Human-in-the-loop**: `interrupt_before=["nodo"]` detiene el grafo antes de ese nodo;
  `app.update_state(config, {"campo": valor})` inyecta la respuesta humana en el estado
  persistido; se reanuda con `.stream()`/`.invoke()` usando el mismo `config`/`thread_id`
  (sin recompilar). Este es el patrón de bajo nivel detrás del nodo `aprobar` de
  `plantilla/agent_harness/graph.py`.

## Tema 5 — Memoria y gestión de contexto

- **Conceptos clave**: *context window* (límite de tokens por request), *thread/session* (aísla
  historiales de conversaciones concurrentes), persistencia (RAM = volátil, disco/BD = sobrevive
  reinicios).
- **`RunnableWithMessageHistory`**: para prototipos simples sin persistencia — envuelve una
  cadena con un `get_session_history(session_id)` que devuelve un `InMemoryChatMessageHistory`.
  Sencillo pero RAM-only, no apto para producción concurrente.
- **LangGraph (recomendado)**: `MessageState` (estado predefinido con `messages: list[BaseMessage]`)
  + `MemorySaver` (checkpointer en RAM) o `SqliteSaver`/Postgres/Redis (checkpointer persistente)
  para memoria entre invocaciones aisladas por `thread_id`.
- **`trim_messages`** (`langchain_core.messages`): ventana deslizante para controlar costo —
  recorta solo lo que se envía al LLM (`strategy="last"`, `max_tokens=N`, `start_on="human"`,
  `include_system=True`), mientras el estado/checkpoint puede seguir guardando el historial
  completo para auditoría. Equivalente conceptual a `ventana_mensajes` /
  `harness/window.py::validar_historial` en `plantilla/`.
- **Memoria vectorial**: para recuerdo de largo plazo por usuario (perfil, preferencias) en vez
  de arrastrar todo el hilo — guardar hechos como `Document` con `metadata={user_id, type, ...}`
  en un vectorstore y recuperar por similitud (`k` chico, filtrado por `user_id`). Se combina con
  memoria de hilo: vectorial da "recuerdo duradero", la ventana deslizante controla el costo del
  turno.

## Tema 6 — Agentes y herramientas (tool calling)

- **Tool**: función externa con nombre, descripción y esquema de entrada/salida que el LLM puede
  invocar. El **tool calling moderno** hace que el modelo devuelva una estructura (`tool_name`,
  `arguments`, `call_id`) en vez de texto libre a parsear — más robusto.
- **Definir una tool** (`@tool` de `langchain_core.tools`, ruta preferida): función con type
  hints obligatorios + docstring clara (la docstring se usa como `description`, y la
  description es lo que el LLM lee para decidir cuándo usarla). Alternativa más verbosa:
  `StructuredTool.from_function(fn=...)`.
- **Buenas prácticas de diseño de tools**: pocas tools bien descritas, sin solapamiento;
  validar inputs (type hints/Pydantic); efectos colaterales controlados (idempotencia o
  `dry_run`); loguear `tool_name`/`arguments`/`duration`/resultado; sandboxear lo peligroso
  (REPL de código) con timeouts y whitelists — mismo espíritu que
  `plantilla/agent_harness/harness/runner.py` y el flag `sensible=True`.
- **Flujo básico de tool calling**: crear LLM que soporte tool calling → `llm.bind_tools([...])`
  → invocar → si el modelo pide una tool, `resp.tool_calls` trae `name`/`args`/`id` → **el código
  ejecuta la tool, no el modelo** → (opcional) reinvocar al LLM con el resultado como mensaje de
  tool para que cierre la respuesta. Es la misma idea de "el modelo propone, el código dispone".
- **`response_format`**: permite que una tool devuelva `(contenido, artifact)` — el contenido va
  al LLM, el artifact queda solo para uso interno (logs, metadata pesada).
- **Ciclo de un agente (ReAct)**: instrucción → pensamiento (LLM) → elección de tool+args →
  ejecución → observación (resultado vuelve al contexto) → repetir hasta respuesta final.
  Guardrails típicos: límite de pasos/iteraciones, presupuesto, timeouts.
- **Agentes en LangGraph (recomendado para producción)**: `langgraph.prebuilt.create_react_agent`
  sustituye al `AgentExecutor` de LangChain clásico; usa `MemorySaver`/checkpointer para estado
  entre pasos y no requiere `agent_scratchpad` manual.
- **Multi-agente con supervisor** (`langgraph_supervisor.create_supervisor`): un supervisor
  decide a qué agente especialista delegar y cuándo parar; topologías: **supervisor** (1
  coordinador + N expertos, la recomendada), **red** (agentes colaboran entre sí, más flexible y
  más frágil), **jerárquica** (varios niveles). Es el mismo patrón que `graph.py::supervisor()` +
  `AgentSpec` en `plantilla/`.
- **Arquitectura "product-ready" de una solución multiagente** (capas, independientes del
  dominio): Interfaz/API (REST + healthcheck) → Orquestación (supervisor+especialistas) →
  Integraciones (búsqueda, mensajería, con reintentos/backoff) → Observabilidad (logs
  estructurados, trazas por `thread_id`, métricas de latencia/éxito) → Seguridad (sandboxes,
  sanitización anti prompt-injection, control de salidas riesgosas) → Persistencia (checkpoints,
  config por entorno). Mapea directo a las carpetas de `plantilla/agent_harness/` (`harness/`,
  `observability.py`, `memory/`, `config.py`).

---

Fuente original: cuaderno de trabajo personal en PDF (fuera del repo). Este archivo es un
resumen condensado para consulta dentro del repo, no una copia literal.
