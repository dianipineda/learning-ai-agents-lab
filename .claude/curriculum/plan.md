# Curriculum Detallado — AI Agents Lab

## Estilo pedagógico
Ejercicios estilo "crucigrama": el aprendiz llena blancos (___BLANK_X___) en código funcional.
Cada blank tiene: concepto teórico, pista, y espacio para que el aprendiz razone la solución.
No dar la respuesta directa — guiar con preguntas socráticas si el aprendiz está atascado.

---

## Fase 1 — Primera llamada a un LLM ✅ COMPLETA
**Archivo:** `fase_1/ejercicio.py`

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
**Archivo:** `fase_2/ejercicio.py`

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
**Archivo:** `fase_3/ejercicio.py`

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
**Archivo:** `fase_4/ejercicio.py`

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
**Archivo:** `fase_5/ejercicio.py`

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
**Archivo:** `fase_6/ejercicio.py`
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

## Fase 7 — Harness / LangGraph 🔜 SIGUIENTE
**Conceptos a cubrir:**
- Frameworks de orquestación vs implementación manual
- LangGraph: nodos, edges, state
- Cuándo vale la pena usar un framework vs código propio

**Pendientes heredados de la Fase 6 (resolver con el state de LangGraph):**
- `crear_reclamo` genera el ID desde el número de pedido (`REC-{últimos 4}`) y no guarda nada: dos reclamos del mismo pedido colisionan en `REC-1001`. Solución: store con IDs únicos (+ opcional tool `consultar_reclamo`).
- El clasificador no tiene memoria y etiqueta mal los seguimientos.
- Edge case de `MAX_ITERACIONES`: el historial termina en `user` y el siguiente turno duplica `user`.
- Extraer texto con `next(b.text for b in content if b.type == "text")`, no `content[0].text` (puede venir un `ThinkingBlock` primero). Fase 5 aún usa `content[0]`.
