# AI Agents Lab

Laboratorio de aprendizaje de ingeniería de agentes de IA con la API de Anthropic.
Ejercicios estilo "crucigrama" por fases (`fase_1/` … `fase_7/`).

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
python fase_1/ejercicio.py
```
