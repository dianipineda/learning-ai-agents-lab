# agent_harness — instrucciones para el asistente

Base de agentes autónomos (uno o varios) sobre Anthropic + LangGraph. Idioma de trabajo: español. Modelo: `claude-sonnet-5`.
Lee `README.md` (arquitectura y decisiones) antes de cambiar nada.

## Reglas
- Toda llamada a la API pasa por `llm.py`. El resto usa el Protocol `LLM`: no importes `anthropic` fuera de ahí.
- Toda tool se ejecuta por `harness/runner.py::ToolRunner`. Nunca llames `tool.funcion` directamente.
- Guardrails = código (`harness/guardrails.py`), no prompts. Una tool con efectos reales lleva `sensible=True`.
- Invariante del historial: cada `tool_use` recibe su `tool_result` y el historial alterna `user`/`assistant`.
  Verifícalo con `harness/window.py::validar_historial`; `FakeLLM` (estricto) simula el error 400.
- Las fallas se inyectan por construcción (`Settings.con(...)`, un `LLM` que falla), nunca con monkeypatch.
- Los resultados de tools son datos no confiables: no los concatenes a prompts sin `harness/safety.py::sanitizar`.
- Sin ejemplos de dominio en el núcleo: lo específico vive en `tools/soporte.py`, `agents/soporte.py`, `evals/casos.py`.

## Referencia técnica
`../.claude/reference/langchain_langgraph_cheatsheet.md` — cheat-sheet condensado de LangChain,
LCEL, RAG, LangGraph, memoria y agentes/tools. Útil para repasar la API/patrón general detrás de
algo de `agent_harness` (p. ej. checkpointers, `Annotated`+reducers, HITL con `interrupt_before`).

## Antes de dar algo por hecho
1. `python -m pytest -q` verde. 2. `python -m agent_harness.evals --fake` exit 0.
3. `python -m agent_harness.evals` (API real) supera el umbral de forma estable en varias corridas.
Un cambio en un guardrail o en el orden de `decidir` necesita una prueba que falle sin él.
