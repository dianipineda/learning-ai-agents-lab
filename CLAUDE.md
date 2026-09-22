# AI Agents Lab — D. Ramirez (d.ramirez@rappi.com)

## Qué es este proyecto
Laboratorio de aprendizaje de ingeniería de agentes de IA usando la API de Anthropic.
Estilo "crucigrama": el aprendiz llena blancos clave en ejercicios guiados.
Objetivo final: construir un orquestador multi-agente autónomo de soporte de pedidos.

## Config técnica
- Model: `claude-sonnet-5`
- Workspace ID: `wrkspc_013t1vonrMTGakoTg7Pj92DB`
- `.env` requiere: `ANTHROPIC_API_KEY` y `ANTHROPIC_WORKSPACE_ID`
- Dependencias: `anthropic`, `python-dotenv`, `langgraph` (ver `requirements.txt`)
- Idioma de trabajo: español

## Estructura del repo
- `ejercicios/fase_N/` — cuaderno con blancos `___BLANK_X___` para quien aprende.
- `soluciones/fase_N/` — las mismas fases resueltas.
- Al crear una fase o ejercicio nuevo: escribir la versión con blancos en `ejercicios/` y la
  resuelta en `soluciones/`, con la misma ruta relativa. Correr siempre desde la raíz.
- Mientras el aprendiz resuelve en `ejercicios/`, no copiar respuestas desde `soluciones/`:
  guiar con pistas.

## Plantilla
`plantilla/` (`agent_harness`) es una base profesional para arrancar agentes propios; NO es un ejercicio (sin blancos) ni parte del curriculum.
Es la referencia recomendada como arquitectura base. Lee `plantilla/README.md` y `plantilla/CLAUDE.md` antes de tocarla. Corre desde `plantilla/`.

## Referencia técnica
`.claude/reference/langchain_langgraph_cheatsheet.md` — cheat-sheet condensado de LangChain,
LCEL, RAG, LangGraph, memoria y agentes/tools. No es parte del curriculum; consultarlo cuando
una fase o `plantilla/` toque alguno de esos temas y haga falta repasar la API/patrón general.

## Estado actual
**Última fase completada:** Fase 7 — Harness / LangGraph
**Siguiente fase:** Fase 8 — Human-in-the-loop y guardrails (luego Fase 9, Fase 10 —el proyecto final: el orquestador multi-agente autónomo— y Fase 11 —endurecerlo para producción—). Los ejercicios de las fases 8 a 11 ya están creados; falta que el aprendiz los resuelva.

## Protocolo de sesión
1. `/clear` entre fases (no dentro de una fase)
2. Al iniciar sesión nueva, el usuario dice: "iniciemos fase X"
3. Yo leo `.claude/curriculum/plan.md` para contexto detallado de la fase
4. Propongo lo que haré y arrancamos

## Fases del curriculum

| # | Tema | Estado |
|---|------|--------|
| 1 | Primera llamada a un LLM | ✅ Completa |
| 2 | Prompt Engineering + Structured Output | ✅ Completa |
| 3 | Tool Calling | ✅ Completa |
| 4 | Agente con memoria | ✅ Completa |
| 5 | Orquestador con 2 agentes | ✅ Completa |
| 6 | Sistema multi-agente completo (Agente de Soporte de Pedidos) | ✅ Completa |
| 7 | Harness / LangGraph | ✅ Completa |
| 8 | Human-in-the-loop y guardrails | 🔜 Pendiente |
| 9 | Evaluación y supervisor multi-agente | 🔜 Pendiente |
| 10 | Proyecto final: el orquestador | 🔜 Pendiente |
| 11 | Agente listo para producción (ventana, streaming, tools seguras) | 🔜 Pendiente |

## Cómo actualizar este archivo
Al completar una fase: cambiar su estado de 🔜 a ✅ y actualizar "Estado actual".
Detalle técnico de cada fase vive en `.claude/curriculum/plan.md`.
