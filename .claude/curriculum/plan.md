# Curriculum Detallado — AI Agents Lab

## Estilo pedagógico
Ejercicios estilo "crucigrama": el aprendiz llena blancos (___BLANK_X___) en código funcional.
Cada blank tiene: concepto teórico, pista, y espacio para que el aprendiz razone la solución.
No dar la respuesta directa — guiar con preguntas socráticas si el aprendiz está atascado.

---

## Fase 1 — Primera llamada a un LLM ✅ COMPLETA
**Archivo:** `ejercicios/fase_1/ejercicio.py` (solución en `soluciones/fase_1/ejercicio.py`)

**Conceptos cubiertos:**
- Qué es una API client library
- Crear cliente `anthropic.Anthropic()`
- Estructura de `messages`: lista de dicts con `role` y `content`
- Roles: `"user"` (tú hablas) / `"assistant"` (historial de Claude)
- Parámetro `max_tokens`
- Extraer texto: `respuesta.content[0].text`
- Multi-turn conversation: cómo construir historial manualmente

**5 blanks resueltos:** import, cliente, dict de messages, llamada `.create()`, extracción `.content[0].text`

**Nota técnica crítica:**
API key identity-linked → requiere header adicional:
```python
cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_013t1vonrMTGakoTg7Pj92DB"}
)
```

---

## Fase 2 — Prompt Engineering + Structured Output ✅ COMPLETA
**Archivo:** `ejercicios/fase_2/ejercicio.py` (solución en `soluciones/fase_2/ejercicio.py`)

**Conceptos cubiertos:**
- System prompt: parámetro `system=` separado del array `messages`
- Prompt engineering: definir formato, enumerar valores permitidos, anticipar edge cases
- JSON Schema en el prompt para forzar output estructurado
- `json.loads()` (string → dict) vs `json.dumps()` (dict → string)
- String immutability en Python: métodos devuelven nuevo valor, no modifican in-place
- Defensive coding: Claude a veces envuelve JSON en ```json ... ``` a pesar del prompt
- Stripping de markdown fences antes de `json.loads()`

**4 blanks resueltos:** system prompt completo (8 campos), parámetro `system=`, `json.loads()`, acceso a `datos['campo']`

**Caso de uso:** clasificador de tickets de soporte con 8 campos estructurados:
`numero_pedido`, `ts_recepcion_ticket`, `estado_percibido_pedido`, `pedido_destinado_a`,
`satisfaccion_usuario_ticket`, `pregunta_usuario`, `sentido_de_urgencia`, `queja_calidad`

**Fence stripping implementado:**
```python
texto_limpio = texto_respuesta.strip()
if texto_limpio.startswith("```"):
    texto_limpio = texto_limpio.split("\n", 1)[1]
    texto_limpio = texto_limpio.rsplit("```", 1)[0]
datos = json.loads(texto_limpio)
```

---

## Fase 3 — Tool Calling ✅ COMPLETA
**Archivo:** `ejercicios/fase_3/ejercicio.py` (solución en `soluciones/fase_3/ejercicio.py`)

**Conceptos cubiertos:**
- Qué son las "tools" / "functions" en el contexto de LLMs
- Cómo definir una tool: nombre, descripción, parámetros (JSON Schema)
- El ciclo tool_use: Claude decide llamar una tool → tú la ejecutas → devuelves resultado → Claude responde
- `stop_reason == "tool_use"` como señal de que Claude quiere usar una herramienta
- Rol `"tool_result"` en el array de messages (role `"user"` con content especial)
- Cuándo Claude llama una tool vs cuándo responde directo

**5 blanks resueltos:** schema de tool (name/description/input_schema), parámetro `tools=`,
detección de `stop_reason == "tool_use"` + extracción de bloque, ejecución de función +
construcción del `tool_result`, segunda llamada con historial completo de 3 mensajes.

**Caso de uso:** agente que consulta el estado de un pedido Rappi.
Función simulada `consultar_estado_pedpi(numero_pedido)` → devuelve dict con estado,
tiempo restante y repartidor.

---

## Fase 4 — Agente con memoria ✅ COMPLETA
**Archivo:** `ejercicios/fase_4/ejercicio.py` (solución en `soluciones/fase_4/ejercicio.py`)

**Conceptos cubiertos:**
- Historial como única "memoria" del LLM: lista `messages` que crece turno a turno
- Loop externo (turno de usuario) + loop interno (ciclo tool_use): patrón doble while
- 4 puntos de append: user input → assistant tool_use → tool_result → assistant final
- Distinción entre `respuesta.content` (para la API, estructura completa) vs `respuesta.content[0].text` (para mostrar al usuario, solo string)
- El `tool_result` va con `"role": "user"` porque es el programador quien se lo entrega a Claude

**6 blanks resueltos:** inicializar `historial = []`, append mensaje usuario, pasar `messages=historial`,
append respuesta intermedia con tool_use, append tool_result, append respuesta final.

---

## Fase 5 — Orquestador con 2 agentes ✅ COMPLETA
**Archivo:** `ejercicios/fase_5/ejercicio.py` (solución en `soluciones/fase_5/ejercicio.py`)

**Conceptos cubiertos:**
- Coordinación entre agentes especializados: Clasificador (JSON `{tipo, numero_pedido}`) + Ejecutor
- Paso de información estructurada entre agentes (la salida del clasificador decide el system prompt del ejecutor)
- System prompt condicional por `tipo` y tools solo para `consulta_pedido`
- Ciclo tool_use dentro de una función que retorna el texto final
- Todo mensaje del historial requiere `content` (error 400 `messages.1.content: Field required` al omitir `respuesta.content` en el mensaje assistant)

**5 blanks resueltos:** system prompt del clasificador, llamada al clasificador, system prompt condicional del ejecutor,
`tools=` condicional, ciclo tool_use con historial de 3 mensajes.

---

## Fase 6 — Sistema multi-agente completo ✅ COMPLETA
**Archivo:** `ejercicios/fase_6/ejercicio.py` (solución en `soluciones/fase_6/ejercicio.py`)
**Objetivo:** "Agente de Soporte de Pedidos" funcional end-to-end, integrando fases 2-5.

**Conceptos a cubrir:**
- Integrar clasificador + ejecutor + memoria + tools en un solo sistema
- Varias tools y despachador `dict nombre → función`
- Loop interno con límite de iteraciones (guardrail) y fallback a humano
- Varios bloques `tool_use` en un mismo turno → un solo mensaje con todos los `tool_result`
- Contexto del clasificador inyectado en el system prompt del ejecutor

**6 blanks:** schema de `crear_reclamo`, despachador `FUNCIONES`, system prompt del ejecutor,
condición de salida del loop, ejecución de todas las tools, memoria entre turnos.

**Lecciones aprendidas:**
- Una función que construye un prompt debe hacer `return`: sin él devuelve `None` y la API responde 400 `system: Input should be a valid array`
- El system prompt debe prohibir inventar no solo datos (estados, IDs) sino también procesos, políticas, canales y acciones que no existen como tool (si no, el modelo alucina "pasos" y ofrece cosas imposibles)
- El clasificador sin memoria etiqueta mal los mensajes de seguimiento (ej. solo "RP-1002" → `consulta_pedido`); el ejecutor lo compensa porque sí ve el historial
- Edge case conocido: si se agotan las `MAX_ITERACIONES`, el historial termina en un `user` y el siguiente turno haría dos `user` seguidos

---

## Fase 7 — Harness / LangGraph ✅ COMPLETA
**Conceptos a cubrir:**
- Frameworks de orquestación vs implementación manual
- LangGraph: nodos, edges, state
- Cuándo vale la pena usar un framework vs código propio

### Ejercicio 1 ✅ — Grafo mínimo `START → clasificar → END`
**Archivo:** `ejercicios/fase_7/ejercicio_1.py` (solución en `soluciones/fase_7/ejercicio_1.py`)

**Lecciones aprendidas:**
- State = `TypedDict` que viaja por el grafo. Solo conserva las claves declaradas: un typo (`mesaje` vs `mensaje`) hace que LangGraph descarte la entrada sin avisar y el nodo falle con `KeyError`.
- Un nodo recibe el state y devuelve solo un dict PARCIAL con lo que cambia. LangGraph mezcla ese dict con el state anterior (por eso `mensaje` sobrevive sin que el nodo lo devuelva). Ventajas: menos código, un nodo no puede borrar campos ajenos, y agregar campos al State no obliga a editar los demás nodos.
- `add_node("nombre", fn)`, `add_edge(origen, destino)`, `START`/`END`, `compile()` → ejecutable, `invoke(state_inicial)` → state final.
- El state vive solo dentro de un `invoke`: cada llamada empieza de cero. Sin checkpointer no hay memoria entre turnos (se ve con el clasificador: "Mi pedido llegó frío" → `queja`, luego "RP-1002" → `consulta_pedido`). Se resuelve en el ejercicio 3.
- Los nodos siguen usando el SDK de Anthropic; LangGraph solo orquesta.

### Ejercicio 2 ✅ — El loop de tools como grafo con ciclo
**Archivo:** `ejercicios/fase_7/ejercicio_2.py` (solución en `soluciones/fase_7/ejercicio_2.py`)

**Lecciones aprendidas:**
- Grafo: `START → clasificar → ejecutor ─(¿tool?)→ tools → ejecutor … → END`. El `for` de la Fase 6 desaparece: el ciclo vive en la forma del grafo, y cada nodo hace una sola cosa (una llamada a Claude, o ejecutar tools).
- Arista condicional: `add_conditional_edges(origen, funcion_de_ruteo, mapa)`. La función de ruteo lee el state y devuelve el NOMBRE del siguiente nodo (o `END`); no modifica el state.
- Sin reducer, un campo devuelto por un nodo REEMPLAZA al anterior. Para "agregar" al `historial` hay que devolver la lista anterior + lo nuevo; devolver solo el mensaje nuevo borraría la conversación.
- Mapa Fase 6 → 7: `if stop_reason != "tool_use"` → función de ruteo; bloque de tools → nodo `tools`; `MAX_ITERACIONES` → `recursion_limit` (`invoke(..., config={"recursion_limit": 10})`); `GraphRecursionError` al excederlo.
- `recursion_limit` cuenta ejecuciones de nodos (incluido `clasificar`), no vueltas del loop.

### Ejercicio 3 ✅ — Memoria con checkpointer
**Archivo:** `ejercicios/fase_7/ejercicio_3.py` (solución en `soluciones/fase_7/ejercicio_3.py`)

**Lecciones aprendidas:**
- Checkpointer: `MemorySaver()` en `builder.compile(checkpointer=memoria)` guarda el state después de cada paso. En producción se cambia por uno persistente (SQLite/Postgres) con la misma API.
- `thread_id` en `config={"configurable": {"thread_id": ...}}` identifica una conversación. Mismo id → carga el state guardado; otro id (comando `nuevo`) → arranca limpio.
- Reducer: `historial: Annotated[list, operator.add]` concatena en vez de reemplazar. Los nodos devuelven SOLO lo nuevo y el input de `invoke` lleva solo el mensaje user de ese turno. Devolver `estado["historial"] + [...]` con reducer DUPLICA el historial (`[A,B] + [A,B,C]`), lo que puede causar mensajes repetidos, `tool_use_id` duplicados y error 400.
- Regla para decidir si un campo lleva reducer: "estado actual de algo" (`stop_reason`, `respuesta`, `clasificacion`) se REEMPLAZA; "registro que crece" (`historial`) se ACUMULA. Si `stop_reason` se acumulara, la función de ruteo dejaría de funcionar.
- El checkpointer serializa el state, por eso los mensajes assistant se guardan como dicts simples (`bloques_a_dict`) y `tools_node` usa `bloque["type"]` en vez de `bloque.type`.
- Clasificador con memoria: recibe la clasificación anterior (`estado.get("clasificacion")`, `None` en el primer turno) junto al mensaje nuevo, así un seguimiento como "RP-1002" conserva el tipo `queja`.
- IDs únicos de reclamo: el store `RECLAMOS` genera `REC-{len+1:04d}`, sin la colisión de la Fase 6.

**Pendientes heredados de la Fase 6:**
- ✅ Resuelto: clasificador sin memoria (checkpointer + clasificación previa).
- ✅ Resuelto: colisión de IDs `REC-1001` (store `RECLAMOS`). Queda opcional una tool `consultar_reclamo`.
- ✅ Resuelto: historial reconstruido a mano (reducer + checkpointer).
- ⏳ Sin verificar: edge case de `recursion_limit`. Tras un `GraphRecursionError` el checkpoint puede quedar terminando en `user`, y el siguiente turno duplicaría `user`. Se prueba bajando `recursion_limit` a 3.
- ⏳ Pendiente: la Fase 5 aún usa `content[0].text`; usar `next(b.text for b in content if b.type == "text")` (puede venir un `ThinkingBlock` primero).

### Comparación final — framework vs código propio
- **LangGraph aportó:** memoria por hilo (`thread_id`), persistencia (cambiar `MemorySaver` por SQLite/Postgres), reducers, y el ciclo del loop de tools expresado como grafo. Lo más valioso: memoria por hilo y persistencia.
- **Costó:** más ceremonia (State, nodos, aristas, compile) sin menos código para un agente de 3 pasos; reglas que se aprenden a golpes (reemplazo vs reducer, claves no declaradas descartadas, mensajes serializables); depuración menos directa que un `print` en un loop; dependencia de versiones (`langchain-core`).
- **LangGraph NO mejora** prompts, tools ni calidad del agente: solo orquesta.
- **Usar LangGraph si:** persistencia real o muchas conversaciones, flujos con ramas/ciclos/varios agentes, human-in-the-loop (pausar y retomar), equipo que mantiene el sistema.
- **Código propio si:** flujo lineal o loop simple, prototipo/un usuario, se quiere control total y trazabilidad simple.
- **Veredicto:** para el agente de soporte actual bastaba el código de la Fase 6; LangGraph se justifica al crecer a multi-agente con escalamiento a humano y conversaciones persistentes. Heurística: no adoptar el framework hasta sentir el dolor que resuelve.

**Pendientes que quedan abiertos al cerrar la Fase 7:** verificar el edge case de `recursion_limit=3` (checkpoint termina en `user`); cambiar `content[0].text` en la Fase 5; tool opcional `consultar_reclamo`.

---

## Fase 8 — Human-in-the-loop y guardrails 🔜 PENDIENTE
**Objetivo:** que el agente sepa cuándo parar, pedir aprobación humana y no ejecutar acciones peligrosas.
**Archivos (a crear al iniciar):** `ejercicios/fase_8/...` (con blancos) y `soluciones/fase_8/...` (resueltos).
**Requisito previo:** cerrar los pendientes de la Fase 7 (edge case `recursion_limit=3`; `content[0].text` de la Fase 5).

**Ejercicios (creados; cada uno incluye resuelto lo anterior):**
1. `ejercicio_1.py` — `interrupt` + checkpointer: pausar antes de `crear_reclamo` y retomar con `Command(resume=...)`. 8 blancos. Trampa: el nodo se re-ejecuta desde el principio al retomar.
2. `ejercicio_2.py` — Guardrails: contador de tokens con reducer (`Annotated[int, operator.add]`), validación de argumentos con `is_error`, y nodo `limite` que corta y cierra el historial (un `tool_use` siempre necesita su `tool_result`). 8 blancos.
3. `ejercicio_3.py` — Robustez: `max_retries`/`timeout` del cliente, captura de `anthropic.APIError` en el nodo (agregando un mensaje assistant para no romper la alternancia user/assistant) y excepciones de tools devueltas como `is_error`. 6 blancos. Cierra en la práctica el edge case pendiente de la Fase 7.
Estado: los 3 ejercicios están creados en `ejercicios/` y `soluciones/`; el aprendiz aún no los resuelve. Verificados con un cliente falso (aprobar/rechazar, argumentos inválidos, presupuesto, falla de API y de tool); sin probar contra la API real.

**Qué debe quedar claro:** la autonomía tiene límites explícitos; el humano decide en los puntos de riesgo; un error de tool no rompe el agente.

---

## Fase 9 — Evaluación y supervisor multi-agente 🔜 PENDIENTE
**Objetivo:** medir la calidad del agente y ensayar la arquitectura del orquestador final.
**Archivos:** `ejercicios/fase_9/ejercicio_1..3.py` y `soluciones/fase_9/ejercicio_1..3.py`.

**Ejercicios (creados; el 3 incluye el 2 resuelto; el 1 es independiente):**
1. **Evaluación** (`ejercicio_1.py`, 7 blancos: 1a, 1b, 2–6): 12 casos etiquetados del clasificador, métrica de precisión, comparación de dos prompts (A mínimo vs B con definiciones) y puerta de calidad (regression gate). Lección: el LLM no es determinista; una diferencia de un caso puede ser ruido.
2. **Supervisor y traspasos** (`ejercicio_2.py`, 8 blancos: 1, 2, 3, 4a, 4b, 5, 6, 7): supervisor con `tool_choice` forzado, especialistas (pedidos/reclamos/pagos) como un solo nodo parametrizado por `estado["agente"]` (system + subconjunto de tools), tool `transferir_a` y nodo `traspasar` que responde el tool_use, cambia el agente activo y limita a `MAX_TRASPASOS`. Historial compartido.
3. **Ensayo general** (`ejercicio_3.py`, 9 blancos: 1, 2, 3a, 3b, 4–8): ejercicio 2 + `interrupt` para `crear_reclamo` + eval de punta a punta (ruta, tools intentadas, efectos reales en `RECLAMOS`) con aprobación automática; modo `--chat` interactivo. Código de salida 0/1 según el umbral.

**Estado:** los 3 ejercicios están creados en `ejercicios/` y `soluciones/`; el aprendiz aún no los resuelve. Verificados solo con un cliente falso (sin probar contra la API real); los blancos solo se comprobaron con `py_compile` y `NameError`. Los guardrails de la fase 8 (tokens, validación, reintentos) no se repiten aquí; el orquestador final debe integrarlos.

**Fuera del curriculum (deliberado):** observabilidad/tracing, streaming y prompt caching (optimizaciones de producción).

## Fase 10 — Proyecto final: el orquestador 🔜 PENDIENTE
**Objetivo:** ensamblar en un solo agente todo lo aprendido y validarlo contra la API real. Es integración guiada, sin conceptos nuevos.
**Archivos:** `ejercicios/fase_10/ejercicio_1..2.py` y `soluciones/fase_10/ejercicio_1..2.py`.

**Ejercicios (creados; el 2 importa el 1: `import ejercicio_1 as orq`):**
1. **El orquestador** (`ejercicio_1.py`, 9 blancos: 1, 2, 3, 4a, 4b, 5, 6, 7, 8): ensamblado completo. Lo nuevo: política por campo del estado (acumular `historial`/`traza`/`tokens_usados`; reiniciar `traspasos`/`aprobado` por turno en el supervisor), orden en `decidir` (limite → traspasar → aprobar → tools), `cerrar_hilo` con `update_state(as_node="limite")` para reparar un hilo cortado por `GraphRecursionError` (cierra el edge case de la fase 7), `hablar(thread_id, ...)` con memoria por hilo y chat con `nuevo`/`salir`. Supervisor y especialista degradan si la API falla.
2. **Evaluación final** (`ejercicio_2.py`, 7 blancos: 1–7): parte A guardrails sin API; parte B 9 casos (consulta pedido/pago, queja aprobada/rechazada, traspaso pagos→reclamos, memoria de 2 turnos, tool caída RP-9999, API caída con cliente inyectado, presupuesto agotado) x `REPETICIONES=3`; puerta: guardrails OK y TODAS las pasadas >= `UMBRAL`. Código de salida 0/1.

**Estado:** ejercicios creados; el aprendiz aún no los resuelve. Verificados solo con un cliente falso (eval 9/9 x3, chat con rechazo/aprobación, hilo roto con `recursion_limit=3` reparado, sin 400); los blancos solo se comprobaron con `py_compile` y `NameError`. Pendiente de este proyecto: la corrida contra la API real (entregable 3).

**Entregables propuestos:**
1. **Ensamblaje:** supervisor + especialistas con traspasos (fase 9) + aprobación humana con `interrupt` (fase 8 ej. 1) + guardrails (presupuesto de tokens, validación de argumentos; fase 8 ej. 2) + robustez (reintentos, timeouts, errores controlados; fase 8 ej. 3) + memoria por hilo con checkpointer (fase 7).
2. **Eval ampliado:** más casos que en la fase 9 ej. 3, incluyendo traspasos, argumentos inválidos, rechazos del humano, tool caída (RP-9999) y API caída; umbral como puerta de calidad.
3. **Prueba contra la API real:** correr el eval y las conversaciones reales, ajustar prompts y umbrales (p. ej. `PRESUPUESTO_TOKENS`) según los resultados, y documentar lo aprendido.

**Criterio de éxito:** el eval supera el umbral de forma estable en varias corridas, ningún camino termina en error 400 ni en traceback, y las acciones con efectos reales nunca se ejecutan sin aprobación.
**Pendientes heredados:** caso límite de la fase 7 con `recursion_limit=3` (cerrado en el ejercicio 1 con `cerrar_hilo`), `content[0].text` de la fase 5 y la tool opcional `consultar_reclamo` (siguen abiertos).
