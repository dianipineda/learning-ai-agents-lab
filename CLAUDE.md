# AI Agents Lab — D. Ramirez (d.ramirez@rappi.com)

## Qué es este proyecto
Laboratorio de aprendizaje de ingeniería de agentes de IA usando la API de Anthropic.
Estilo "crucigrama": el aprendiz llena blancos clave en ejercicios guiados.
Objetivo final: construir un orquestador multi-agente autónomo de soporte de pedidos.

## Config técnica
- Model: `claude-sonnet-5`
- Workspace ID: `wrkspc_013t1vonrMTGakoTg7Pj92DB`
- `.env` requiere: `ANTHROPIC_API_KEY` y `ANTHROPIC_WORKSPACE_ID`
- Dependencias: `anthropic`, `python-dotenv` (ver `requirements.txt`)
- Idioma de trabajo: español

## Estado actual
**Última fase completada:** Fase 4 — Agente con memoria
**Siguiente fase:** Fase 5 — Orquestador con 2 agentes

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
| 5 | Orquestador con 2 agentes | 🔜 Siguiente |
| 6 | Sistema multi-agente completo (Agente de Soporte de Pedidos) | ⏳ Pendiente |
| 7 | Harness / LangGraph | ⏳ Pendiente |

## Cómo actualizar este archivo
Al completar una fase: cambiar su estado de 🔜 a ✅ y actualizar "Estado actual".
Detalle técnico de cada fase vive en `.claude/curriculum/plan.md`.
