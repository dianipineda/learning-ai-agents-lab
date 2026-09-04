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

## Fase 3 — Tool Calling 🔜 SIGUIENTE
**Archivo a crear:** `fase_3/ejercicio.py`

**Conceptos a cubrir:**
- Qué son las "tools" / "functions" en el contexto de LLMs
- Cómo definir una tool: nombre, descripción, parámetros (JSON Schema)
- El ciclo tool_use: Claude decide llamar una tool → tú la ejecutas → devuelves resultado → Claude responde
- `stop_reason == "tool_use"` como señal de que Claude quiere usar una herramienta
- Rol `"tool"` / `"tool_result"` en el array de messages
- Cuándo Claude llama una tool vs cuándo responde directo

**Blanks propuestos:**
1. Definir el schema de una tool (dict con name, description, input_schema)
2. Pasar `tools=` a `.messages.create()`
3. Detectar `stop_reason == "tool_use"` y extraer `tool_use` block
4. Ejecutar la función real y construir el mensaje `tool_result`
5. Segunda llamada con el resultado para que Claude genere respuesta final

**Caso de uso sugerido:** agente que puede consultar el estado de un pedido
(función simulada `consultar_estado_pedido(numero_pedido)` → devuelve dict con estado)

---

## Fase 4 — Agente con memoria ⏳ PENDIENTE
**Conceptos a cubrir:**
- Mantener historial de conversación entre turnos (lista `messages` que crece)
- State management: qué guardar, cuándo limpiar
- Loop conversacional: input del usuario → append → llamada → append respuesta → repetir

---

## Fase 5 — Orquestador con 2 agentes ⏳ PENDIENTE
**Conceptos a cubrir:**
- Coordinación entre agentes especializados
- Agente clasificador + agente ejecutor
- Paso de información estructurada entre agentes
- Cuándo usar un agente vs una función

---

## Fase 6 — Sistema multi-agente completo ⏳ PENDIENTE
**Objetivo:** "Agente de Soporte de Pedidos" funcional end-to-end
Sistema completo integrando todas las fases anteriores.

---

## Fase 7 — Harness / LangGraph ⏳ PENDIENTE
**Conceptos a cubrir:**
- Frameworks de orquestación vs implementación manual
- LangGraph: nodos, edges, state
- Cuándo vale la pena usar un framework vs código propio
