# AI Agents Lab

Laboratorio de aprendizaje de ingeniería de agentes de IA con la API de Anthropic.
Ejercicios estilo "crucigrama" por fases (`fase_1` … `fase_11`; la fase 10 es el proyecto final y la 11 lo endurece para producción) más una **plantilla lista para usar** en `plantilla/`, en las carpetas `ejercicios/` y `soluciones/`.

## Estructura del repositorio

```
ejercicios/    ← cuaderno de ejercicios: código con blancos ___BLANK_X___ para que TÚ los resuelvas
  fase_1/ … fase_11/
soluciones/    ← las mismas fases ya resueltas, para comparar o desatascarte
  fase_1/ … fase_11/
```

**Cómo usarlo para aprender:**

1. Abre un archivo de `ejercicios/` y lee las instrucciones y pistas de cada blanco.
2. Reemplaza cada `___BLANK_X___` por tu código. Mientras quede alguno, el programa falla
   con `NameError`.
3. Ejecútalo y compara con lo esperado en "Pruebas sugeridas por fase".
4. Si te atascas, revisa el mismo archivo en `soluciones/`. Intenta primero por tu cuenta.

Ambas carpetas se ejecutan igual, siempre desde la raíz del repo.

## Instalación

### 1. Entorno nuevo (recomendado)

Usa un entorno dedicado al lab. `langgraph` (Fase 7) requiere `langchain-core>=1.4`,
que choca con versiones antiguas de `langchain` si comparten entorno con otros proyectos.

```bash
conda create -n ai-agents-lab python=3.11 -y
conda activate ai-agents-lab
pip install -r requirements.txt
```

Esto instala `anthropic`, `python-dotenv` y `langgraph`, sin conflictos.

### 2. Variables de entorno

Crea un archivo `.env` en la raíz del repo (ya está en `.gitignore`, no se sube a git):

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_WORKSPACE_ID=wrkspc_...
```

**Cómo obtenerlas** (en la [Anthropic Console](https://console.anthropic.com)):

- `ANTHROPIC_API_KEY`: ve a **Settings → API Keys → Create Key**. La clave se muestra
  una sola vez al crearla; cópiala de inmediato al `.env`.
- `ANTHROPIC_WORKSPACE_ID`: ve a **Settings → Workspaces**, abre el workspace donde
  creaste la clave y copia su ID (empieza por `wrkspc_`).

Los nombres exactos de los menús pueden cambiar con el tiempo. Si no los encuentras,
busca "API Keys" y "Workspaces" en la Console.

Si tu clave está vinculada a tu identidad (no a un workspace), la API exige el header
`anthropic-workspace-id`. Por eso el código crea el cliente así:

```python
cliente = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": "wrkspc_..."}
)
```

### 3. Ejecutar un ejercicio

Con `ai-agents-lab` activo, desde la raíz del repo:

```bash
python ejercicios/fase_1/ejercicio.py     # tu versión con blancos
python soluciones/fase_1/ejercicio.py     # la versión resuelta
```

## Pruebas sugeridas por fase

Para cada fase: qué ejecutar, qué escribir y qué deberías ver. Los comandos usan `ejercicios/`;
sustituye por `soluciones/` para correr la versión resuelta. Si el resultado difiere,
revisa primero que no quede ningún `___BLANK_X___` sin llenar (falla con `NameError`).
Los ejercicios interactivos terminan con `salir`.

Las respuestas de Claude varían en redacción; lo que debe coincidir es el contenido
(estados, IDs, tipos, `stop_reason`).

### Fase 1 — Primera llamada (`ejercicios/fase_1/ejercicio.py`)

No es interactivo: se ejecuta y termina.

- **Ejecuta:** `python ejercicios/fase_1/ejercicio.py`
- **Esperado:** una oración en español sobre qué es Claude, y una línea final
  `[Meta] Tokens usados — entrada: N | salida: M`.
- **Prueba extra:** cambia `max_tokens` a `10`. La respuesta debe salir cortada a media frase.
- **Si falla:** un error de autenticación o de workspace apunta al `.env` o al header
  `anthropic-workspace-id`.

### Fase 2 — Structured Output (`ejercicios/fase_2/ejercicio.py`)

No es interactivo.

- **Ejecuta:** `python ejercicios/fase_2/ejercicio.py`
- **Esperado:** el ticket clasificado y luego el JSON completo, con estos valores para el
  mensaje de ejemplo:
  - `numero_pedido`: `45231`
  - `estado_percibido_pedido`: `"sin llegar"`
  - `sentido_de_urgencia`: `"alto"`
  - `satisfaccion_usuario_ticket`: `"muy molesto"`
  - `queja_calidad`: `null`
- **Prueba extra:** cambia `mensaje_cliente` por un agradecimiento ("Llegó todo perfecto,
  gracias"). Debe dar `estado_percibido_pedido: "recibido"` y urgencia `"bajo"`.
- **Si falla:** `json.JSONDecodeError` significa que Claude devolvió texto extra o Markdown.
  Mira la línea `DEGUG:` para ver el texto crudo.

### Fase 3 — Tool Calling (`ejercicios/fase_3/ejercicio.py`)

No es interactivo.

- **Ejecuta:** `python ejercicios/fase_3/ejercicio.py`
- **Esperado:**
  - `stop_reason: tool_use`
  - la tool `consultar_estado_pedido` con `{'numero_pedido': 'RP-1001'}`
  - el resultado `en_camino`, 12 min, `Carlos M.`
  - una respuesta final que menciona esos datos
- **Prueba extra 1:** cambia el pedido a `RP-9999`. La función devuelve `no_encontrado` y
  Claude debe decirlo sin inventar nada.
- **Prueba extra 2:** cambia el mensaje a `Hola`. No debe llamar la tool y debe imprimir
  `Claude (sin tool): ...`.

### Fase 4 — Agente con memoria (`ejercicios/fase_4/ejercicio.py`)

- **Ejecuta:** `python ejercicios/fase_4/ejercicio.py`
- **Prueba:**
  1. `¿Cómo va mi pedido RP-1001?` → en camino, 12 min, Carlos M. (verás la línea `[tool]`).
  2. `¿Y el RP-1002?` → entregado. Entiende el "y el" gracias al historial.
  3. `¿Cuál fue el primer pedido que te pregunté?` → responde `RP-1001` **sin** llamar
     ninguna tool. Esto confirma que la memoria funciona.
- **Si falla:** si en el paso 3 no recuerda nada, falta guardar la respuesta final en el
  historial (BLANK 6).

### Fase 5 — Orquestador con 2 agentes (`ejercicios/fase_5/ejercicio.py`)

En cada turno verás primero `[clasificador] → {...}` y luego la respuesta del ejecutor.

| Escribe | Clasificador | Esperado del ejecutor |
|---------|--------------|-----------------------|
| `Hola, buenas tardes` | `saludo`, `numero_pedido: null` | Saludo cálido, sin tools |
| `¿Dónde está mi pedido RP-1001?` | `consulta_pedido`, `RP-1001` | Consulta la tool: en camino, 12 min |
| `Mi pedido RP-1003 llegó frío y estoy muy molesto` | `queja`, `RP-1003` | Disculpa y siguiente paso, sin tools |
| `¿Cuál es la capital de Francia?` | `otro` | Explica que solo ayuda con pedidos |

- **Limitación a observar:** no hay memoria entre turnos. Escribe `Mi pedido llegó frío` y
  luego `RP-1002`. El segundo mensaje se clasifica como `consulta_pedido`, porque el
  clasificador no ve el mensaje anterior.

### Fase 6 — Sistema multi-agente completo (`ejercicios/fase_6/ejercicio.py`)

- **Ejecuta:** `python ejercicios/fase_6/ejercicio.py`
- **Prueba:**
  1. `Mi pedido llegó frío` → clasifica `queja` y **pide el número de pedido** sin usar tools.
  2. `RP-1002` → el clasificador dice `consulta_pedido` (limitación), pero el ejecutor ve el
     historial: consulta el pedido, registra el reclamo y entrega el ID `REC-1002`.
  3. `Mi pedido RP-1001 no llegó y necesito que registren un reclamo` → verás
     `consultar_estado_pedido` y luego `crear_reclamo`, y un ID `REC-1001`.
  4. Repite el paso 3 con otro motivo → el ID sale **igual** (`REC-1001`). Es la colisión
     conocida: el ID se calcula a partir del pedido. Se corrige en la Fase 7, ejercicio 3.
- **Guardrail:** el loop interno se corta a las `MAX_ITERACIONES` (5) y ofrece pasar a un
  agente humano. Baja el valor a `1` para provocarlo con una queja con número.

### Fase 7 — LangGraph (`ejercicios/fase_7/`)

Requiere `langgraph` (viene en `requirements.txt`). Ejecuta cada ejercicio por separado.

**Ejercicio 1 — Grafo mínimo (`ejercicios/fase_7/ejercicio_1.py`)**

- **Ejecuta:** `python ejercicios/fase_7/ejercicio_1.py`
- **Prueba:** `Mi pedido llegó frío`, luego `RP-1002`, luego `Hola`.
- **Esperado:** en cada turno se imprime el `state final` con `mensaje` y `clasificacion`.
  Debe salir `queja`, luego `consulta_pedido` (sin memoria), luego `saludo`.
- **Si falla:** `KeyError: 'mensaje'` indica un typo en el nombre del campo del State.

**Ejercicio 2 — El loop de tools como grafo (`ejercicios/fase_7/ejercicio_2.py`)**

- **Ejecuta:** `python ejercicios/fase_7/ejercicio_2.py`
- **Prueba 1:** `¿Cómo va mi pedido RP-1001?`
- **Esperado:** la secuencia `[clasificador]` → `[ejecutor] stop_reason=tool_use` →
  `[tools] consultar_estado_pedido(...)` → `[ejecutor] stop_reason=end_turn`, y una respuesta
  con el estado del pedido. Esa secuencia es el ciclo del grafo.
- **Prueba 2:** `Mi pedido RP-1001 llegó frío, quiero un reclamo`. Debe haber dos rondas de
  tools (consultar y luego crear reclamo) antes de la respuesta final.
- **Prueba 3 (guardrail):** cambia `recursion_limit` a `3` y repite la prueba 1. Debe
  salir el mensaje de "agente humano": `clasificar`, `ejecutor` y `tools` ya son 3 pasos,
  y el segundo `ejecutor` excede el límite (`GraphRecursionError`).
- **Limitación a observar:** cada turno empieza de cero. Sin memoria, `RP-1002` solo no
  recuerda la queja anterior. Se resuelve en el ejercicio 3.

**Ejercicio 3 — Memoria con checkpointer (`ejercicios/fase_7/ejercicio_3.py`)**

- **Ejecuta:** `python ejercicios/fase_7/ejercicio_3.py`
- **Prueba (en orden, sin escribir `nuevo`):**
  1. `Mi pedido llegó frío` → `queja` y pide el número de pedido.
  2. `RP-1002` → el clasificador **mantiene** `queja` (en el ejercicio 1 daba
     `consulta_pedido`). El ejecutor consulta el pedido, crea el reclamo y entrega `REC-0001`.
  3. `Tuve otro problema con RP-1002, llegó incompleto` → crea `REC-0002`. Los IDs ya son
     únicos, sin la colisión de la Fase 6.
  4. `¿Cuál fue el ID de mi primer reclamo?` → responde `REC-0001` sin llamar tools.
     Esto confirma la memoria.
  5. `nuevo` y luego `¿Cuál fue el ID de mi primer reclamo?` → en el hilo nuevo **no** debe
     recordarlo. Cambiar el `thread_id` da una conversación limpia.
- **Prueba de edge case (opcional):** baja `recursion_limit` a `3`, manda una queja con
  número y luego otro mensaje en el mismo hilo. Puede fallar con error 400 por dos mensajes
  `user` seguidos, porque el checkpoint quedó a mitad del ciclo. Es un pendiente heredado
  de la Fase 6.
- **Si falla:** un error al importar `MemorySaver` o al serializar el state indica que
  `langgraph` está desactualizado. Prueba `pip install -U langgraph`.

### Fase 8 — Human-in-the-loop y guardrails (`ejercicios/fase_8/`)

**Ejercicio 1 — Aprobación humana con `interrupt` (`ejercicios/fase_8/ejercicio_1.py`)**

- **Ejecuta:** `python ejercicios/fase_8/ejercicio_1.py`
- **Prueba 1 (tool segura):** `¿Cómo va mi pedido RP-1001?`
- **Esperado:** no hay pausa. Se ve `[tools] consultar_estado_pedido(...)` y la respuesta con
  el estado del pedido. `consultar_estado_pedido` no está en `SENSIBLES`, así que no pasa por `aprobar`.
- **Prueba 2 (aprobar):** `Mi pedido RP-1001 llegó tarde, quiero un reclamo`, y responde `s`.
- **Esperado:** se imprime `⏸ Acción pendiente de aprobación: - crear_reclamo({...})` y el
  programa espera. Al aprobar aparece `[tools] crear_reclamo(...)` y el agente entrega `REC-0001`.
- **Prueba 3 (rechazar):** repite la queja en otra conversación (`nuevo`) y responde `n`.
- **Esperado:** aparece `[tools] crear_reclamo RECHAZADA por el humano`. No se crea ningún
  reclamo y el agente explica que no se pudo registrar y que un humano lo contactará, sin reintentar.
- **Prueba 4 (pausa y estado):** justo cuando pide aprobación, la conversación queda detenida
  en el checkpointer. Si respondes `s`, sigue en el mismo hilo sin repetir la consulta del pedido.
- **Si falla:**
  - Si el grafo nunca se detiene y crea el reclamo directo, revisa que `decidir` devuelva
    `"aprobar"` y que el mapa de `add_conditional_edges` incluya esa salida.
  - Si sale un error de checkpointer al pausar, `compile()` necesita `checkpointer=`.
  - `KeyError: '__interrupt__'` o un `AttributeError` sobre `.value` indican que el `while`
    de 5a no está comprobando bien la clave `"__interrupt__"` del resultado.
  - Un `NameError` con `___BLANK_X___` significa que queda un blanco sin resolver.

**Ejercicio 2 — Guardrails: validación y presupuesto de tokens (`ejercicios/fase_8/ejercicio_2.py`)**

Incluye la aprobación humana del ejercicio 1 ya resuelta. Los blancos nuevos son el contador
de tokens, la validación de argumentos y el corte por presupuesto.

- **Ejecuta:** `python ejercicios/fase_8/ejercicio_2.py`
- **Prueba 1 (todo normal):** `Mi pedido RP-1001 llegó tarde, quiero un reclamo`, y aprueba con `s`.
- **Esperado:** en cada `[ejecutor]` se imprime `tokens acumulados=N/6000` y el número solo sube.
  Se crea `REC-0001`. El contador suma las llamadas del ejecutor y también las del clasificador.
- **Prueba 2 (argumento inválido):** `Quiero un reclamo por el pedido de ayer, llegó frío`.
- **Esperado:** Claude no tiene un número válido, así que debería pedírtelo. Si igual intenta
  `crear_reclamo` con algo como `"el de ayer"`, verás `[tools] crear_reclamo INVÁLIDA: numero_pedido
  inválido...` **sin** la pausa de aprobación (no se molesta al humano por una llamada que se
  rechaza), y Claude corrige el argumento o te pregunta.
- **Prueba 3 (presupuesto):** baja `PRESUPUESTO_TOKENS` a `1500` y repite la prueba 1.
- **Esperado:** tras la primera respuesta del ejecutor con una tool, el agente responde
  `Alcanzamos el límite de esta conversación. Un agente humano te contactará.` y no ejecuta la tool.
  Escribe otro mensaje en el mismo hilo: no debe dar error 400 (el nodo `limite` cierra el historial
  con un `tool_result` y un mensaje assistant). Con `nuevo` el contador vuelve a 0.
- **Si falla:**
  - Un error 400 tras el límite indica que `limite` dejó un `tool_use` sin `tool_result`.
  - Si `tokens_usados` siempre vale lo de la última llamada, falta el reducer en el State (blanco 1).
  - Si el corte nunca ocurre, revisa la condición de 5a y que el mapa de 5b incluya `"limite"`.
  - Si el pedido `RP-12` se acepta como válido, revisa el patrón del blanco 3 (`re.fullmatch`,
    no `re.match`).

**Ejercicio 3 — Robustez: reintentos, timeouts y errores controlados (`ejercicios/fase_8/ejercicio_3.py`)**

Incluye todo lo anterior resuelto. Los blancos nuevos son los parámetros del cliente y la captura
de errores en el ejecutor y en las tools.

- **Ejecuta:** `python ejercicios/fase_8/ejercicio_3.py`
- **Prueba 1 (tool que falla):** `¿Cómo va mi pedido RP-9999?`
- **Esperado:** `[tools] consultar_estado_pedido FALLÓ: TimeoutError: ...` y el agente explica que
  el sistema de pedidos no responde. No hay traceback. Sin el `try/except` del blanco 3, el programa
  se cae con `TimeoutError`.
- **Prueba 2 (API caída):** cierra el programa y ejecútalo con la URL rota:
  `ANTHROPIC_BASE_URL=http://localhost:9 python ejercicios/fase_8/ejercicio_3.py`, luego escribe `Hola`.
- **Esperado:** el clasificador avisa que falló y usa una clasificación neutra; el ejecutor imprime
  `la API falló: APIConnectionError` (tarda unos segundos por los reintentos) y el agente responde
  `Tuve un problema técnico...`. El programa sigue vivo.
- **Prueba 3 (recuperación):** en la misma ejecución con la URL rota, escribe otro mensaje. Debe
  fallar limpio de nuevo, sin error 400. Eso demuestra que el historial sigue alternando
  user/assistant tras el fallo (el nodo agrega un mensaje assistant aunque falle).
  Después vuelve a ejecutarlo con la URL normal y comprueba que todo funciona.
- **Si falla:**
  - Un error 400 en el turno posterior a la falla indica que el `except` del ejecutor no agregó
    un mensaje assistant a `historial`.
  - Si tarda mucho en fallar, revisa `max_retries` y `timeout` del cliente.
  - Un `TypeError` sobre un argumento no esperado del cliente indica un nombre mal escrito en el blanco 1.
  - Con `ANTHROPIC_BASE_URL` rota puede aparecer `APIConnectionError` incluso en `clasificar`; es
    lo esperado, el clasificador está preparado para degradarse.

### Fase 9 — Evaluación y supervisor multi-agente (`ejercicios/fase_9/`)

**Ejercicio 1 — Evaluación de prompts (`ejercicios/fase_9/ejercicio_1.py`)**

Un eval fijo (12 casos con etiqueta) que compara dos prompts del clasificador. Blancos: etiquetas
del último caso, criterio de acierto, precisión, correr ambos prompts, elegir el mejor y la puerta
de calidad.

- **Ejecuta:** `python ejercicios/fase_9/ejercicio_1.py`
- **Esperado:** precisión por prompt y la lista de fallos con `esperado` vs `obtenido`. Normalmente B
  ≥ A; el A suele fallar en quejas que mencionan el estado o cobros. Termina con `Gana: ...` y si el
  candidato B se acepta.
- **Prueba 1:** córrelo 2–3 veces. Si un caso cambia entre corridas, es ruido del modelo.
- **Prueba 2:** empeora B a propósito (borra las definiciones) y comprueba que la puerta lo RECHAZA.
- **Si falla:**
  - `KeyError` en `acerto`: usa `.get()` sobre `obtenido`.
  - `TypeError` en `max`: el `key=` debe recibir el nombre del prompt y devolver su precisión.

**Ejercicio 2 — Supervisor y traspasos (`ejercicios/fase_9/ejercicio_2.py`)**

Equipo de tres agentes (pedidos, reclamos, pagos) coordinados por un supervisor con `tool_choice`
forzado. Blancos: `tool_choice`, extraer el agente, system del especialista, rechazo y destino del
traspaso, detección del traspaso y cableado del grafo.

- **Ejecuta:** `python ejercicios/fase_9/ejercicio_2.py`
- **Prueba 1:** `¿Cómo va mi pedido RP-1001?` → `Ruta: pedidos`.
- **Prueba 2:** `Me cobraron doble el pedido RP-1001` → `Ruta: pagos` (y, si detecta el duplicado y
  pides reclamar, `pagos → reclamos`).
- **Prueba 3 (traspaso):** `Me cobraron doble el RP-1001, quiero registrar un reclamo` → debe verse
  `[traspaso] pagos → reclamos` y la ruta con los dos agentes.
- **Prueba 4:** `Quiero reclamar` → el agente de reclamos pide el número de pedido, sin usar tools.
- **Si falla:**
  - Error 400 sobre `tool_use` sin `tool_result`: el nodo `traspasar` debe responder la llamada.
  - Bucle hasta `GraphRecursionError`: revisa la condición del blanco 4a (tope de traspasos).
  - `KeyError` con `END`: el mapa del blanco 6 debe incluirlo.

**Ejercicio 3 — Ensayo general (`ejercicios/fase_9/ejercicio_3.py`)**

Supervisor + aprobación humana con `interrupt` + eval de punta a punta (ruta, tools intentadas y
efectos reales). Incluye el ejercicio 2 resuelto.

- **Ejecuta el eval:** `python ejercicios/fase_9/ejercicio_3.py` (código de salida 0 si supera el 80 %).
- **Esperado:** 5 casos con `✓/✗` por ruta, tools y efectos, y `APROBADO`/`RECHAZADO`. El caso
  "queja rechazada" debe intentar `crear_reclamo` pero dejar 0 reclamos creados.
- **Modo interactivo:** `python ejercicios/fase_9/ejercicio_3.py --chat` (apruebas o rechazas a mano).
- **Nota:** el LLM no es determinista; un `✗` aislado puede ser ruido. Corre el eval varias veces
  antes de tocar prompts.
- **Si falla:**
  - `RECHAZADO` con `efectos` en `False`: revisa que `aprobar` use el resultado de `interrupt`.
  - `TypeError` al iterar en el blanco 4: el primer mensaje del historial trae `content` como string;
    filtra por `role == "assistant"`.
  - Un caso de ruta falla siempre: mira qué eligió el supervisor antes de culpar al eval.

### Fase 10 — Proyecto final: el orquestador (`ejercicios/fase_10/`)

Integración guiada, sin conceptos nuevos: supervisor + especialistas con traspasos + aprobación
humana + guardrails + robustez + memoria por hilo. Los dos ejercicios van en orden (el 2 importa el 1).

**Ejercicio 1 — El orquestador (`ejercicios/fase_10/ejercicio_1.py`)** · 9 blancos: 1, 2, 3, 4a, 4b, 5, 6, 7, 8

Lo nuevo al juntar todo: qué campos del estado se acumulan y cuáles se reinician por turno, el orden
de decisiones en `decidir` (presupuesto → traspaso → aprobación → tools) y la reparación de un hilo
cortado por `GraphRecursionError` (`cerrar_hilo`, el edge case pendiente de la fase 7).

- **Ejecuta:** `python ejercicios/fase_10/ejercicio_1.py` (`nuevo` abre otra conversación, `salir` termina).
- **Prueba sugerida:** "Mi pedido llegó frío y quiero un reclamo" → luego "Es el RP-1002" (memoria de hilo) →
  responde `s` o `n` a la aprobación. Prueba también `¿Cómo va el RP-9999?` (tool caída).
- **Si falla:**
  - `NameError: ___BLANK_X___`: aún queda un blanco por resolver.
  - Error 400 en el segundo mensaje de un hilo: el historial dejó un `tool_use` sin `tool_result` o dos `user` seguidos (blancos 3 y 7).
  - Un reclamo aprobado en un mensaje vale para el siguiente: falta reiniciar `aprobado` (blanco 2).
  - `Estado` no suma tokens: falta el reducer del blanco 1.

**Ejercicio 2 — Evaluación final (`ejercicios/fase_10/ejercicio_2.py`)** · 7 blancos: 1–7

Parte A: pruebas de guardrails sin API. Parte B: 9 casos de punta a punta (consultas, traspaso, rechazo
humano, memoria de 2 turnos, tool caída, API caída, presupuesto agotado) repetidos 3 veces; solo se
aprueba si TODAS las pasadas superan el 80 %.

- **Ejecuta:** `python ejercicios/fase_10/ejercicio_2.py` (código de salida 0 = listo, 1 = no listo). Usa la API real.
- **Esperado:** guardrails `✓`, 3 pasadas con `✓/✗` por ruta, tools, efectos y final, y `LISTO PARA PRODUCCIÓN`.
- **Si falla:** un `✗` aislado puede ser ruido del LLM; mira la traza del caso antes de tocar prompts.
  Ajusta `PRESUPUESTO_TOKENS` en el ejercicio 1 si "presupuesto" corta conversaciones normales.

### Fase 11 — Agente listo para producción (`ejercicios/fase_11/`)

Extensión de la fase 10 a partir de los huecos detectados frente al cuaderno de LangChain/LangGraph. Los 5
ejercicios son **independientes y no usan la API** (se prueban sin gastar); cada uno termina con código
de salida 0 (OK) o 1 (algún chequeo falló). Conviene tener resuelta la fase 10 antes, pero no es requisito técnico.

| # | Archivo | Tema | Blancos |
|---|---------|------|---------|
| 1 | `ejercicio_1.py` | Ventana deslizante: recortar el historial sin romper turnos ni pares `tool_use`/`tool_result` | 6 |
| 2 | `ejercicio_2.py` | Streaming con LangGraph: `updates`, `values`, `custom` e `interrupt` dentro del stream | 7 |
| 3 | `ejercicio_3.py` | Tools seguras: idempotencia de `crear_reclamo`, circuit breaker y métricas (reloj inyectado) | 10 |
| 4 | `ejercicio_4.py` | Resultados de tools no confiables: sobre de datos, escape de etiquetas, límite de tamaño, prompt injection | 4 |
| 5 | `ejercicio_5.py` | **Opcional.** Memoria de largo plazo por usuario: dedupe, TTL, aislamiento, privacidad | 4 |

- **Ejecuta** (uno por uno): `python ejercicios/fase_11/ejercicio_N.py`
- **Esperado:** una lista de `✓` y `Resultado: OK`.
- **Si falla:**
  - `NameError: ___BLANK_X___`: aún queda un blanco por resolver.
  - Ej. 1: si "toda ventana es válida" falla, tu corte parte un turno o empieza con un `tool_result`.
  - Ej. 2: el chunk de `updates` trae solo lo que devolvió el nodo; el estado acumulado sale en `values`.
  - Ej. 3: un fallo no debe guardarse como "ya hecho", o el reintento nunca se ejecuta.
  - Ej. 4: detectar sobre el texto crudo (antes de recortar) y neutralizar las etiquetas antes de recortar.
- **Reto opcional final:** integrar las piezas en el orquestador de la fase 10 (ventana en `supervisor`/`especialista`,
  `EjecutorSeguro` alrededor de las tools, `armar_tool_result` para los resultados).

### Plantilla — `agent_harness` (`plantilla/`)

Base profesional para arrancar un agente autónomo propio (uno o varios agentes) con el *harness* completo. Destila las fases 7 a 11
en un paquete modular: config por entorno, cliente LLM intercambiable, tools con política (sensible / validación / idempotencia),
`ToolRunner` como única puerta de ejecución, ventana deslizante, circuit breaker, sanitización de resultados, memoria por hilo (SQLite)
y por usuario, logs JSON por `thread_id`, streaming de eventos y un eval con puerta de calidad.

- **Ejecuta** (desde `plantilla/`): `python -m pytest -q` · `python -m agent_harness.evals --fake` · `python -m agent_harness.evals` (API real) · `python -m agent_harness` (chat).
- **Léela primero:** `plantilla/README.md` (arquitectura y decisiones) y `plantilla/CLAUDE.md` (reglas para el asistente).
- **Para usarla en otro proyecto:** cópiala o referencia `@plantilla/` desde Claude Code.
- **Estado:** 48 pruebas verdes con un `FakeLLM`; **no se ha corrido contra la API real**.
- No es material de ejercicios: no tiene blancos y no forma parte del curriculum.

---
