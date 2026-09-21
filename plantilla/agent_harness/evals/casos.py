"""Casos de evaluación de punta a punta (dominio de EJEMPLO: soporte de pedidos).

Cada caso:
  mensajes    → turnos del usuario, en el MISMO hilo (memoria)
  agente      → primer agente elegido por el supervisor
  termina_en  → (opcional) último agente de la traza (traspasos)
  tools       → (opcional) tools de negocio que se INTENTARON usar (deben ser exactamente estas)
  reclamos    → cuántos reclamos deben haberse CREADO de verdad
  aprobar     → qué decide el "humano automático" cuando se le pide aprobación
  stop_reason → (opcional) cómo debe terminar el grafo
  responde_con→ (opcional) texto que debe aparecer en la respuesta final
  presupuesto / falla_api → fallas que se inyectan
"""

CASOS = [
    {"nombre": "consulta de pedido", "mensajes": ["¿Cómo va mi pedido RP-1001?"],
     "agente": "pedidos", "tools": {"consultar_estado_pedido"}, "reclamos": 0},
    {"nombre": "consulta de pago", "mensajes": ["¿Ya me cobraron el pedido RP-1002?"],
     "agente": "pagos", "tools": {"consultar_pago"}, "reclamos": 0},
    {"nombre": "queja aprobada", "mensajes": ["Mi pedido RP-1002 llegó frío y quiero registrar un reclamo"],
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 1, "aprobar": True},
    {"nombre": "queja rechazada por el humano", "mensajes": ["Mi pedido RP-1003 llegó incompleto y quiero registrar un reclamo"],
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 0, "aprobar": False},
    {"nombre": "traspaso pagos → reclamos",
     "mensajes": ["Me cobraron dos veces el pedido RP-1001 y quiero un reclamo"],
     "agente": "pagos", "termina_en": "reclamos", "tools": {"consultar_pago", "consultar_estado_pedido", "crear_reclamo"},
     "reclamos": 1, "aprobar": True},
    {"nombre": "memoria de hilo (2 turnos)",
     "mensajes": ["Mi pedido llegó frío y quiero registrar un reclamo", "Es el RP-1002"],
     "agente": "reclamos", "tools": {"consultar_estado_pedido", "crear_reclamo"}, "reclamos": 1, "aprobar": True},
    {"nombre": "tool caída (RP-9999)", "mensajes": ["¿Cómo va mi pedido RP-9999?"],
     "agente": "pedidos", "tools": {"consultar_estado_pedido"}, "reclamos": 0, "responde_con": "problema técnico"},
    {"nombre": "API caída", "mensajes": ["¿Cómo va mi pedido RP-1001?"],
     "agente": "pedidos", "reclamos": 0, "falla_api": True, "stop_reason": "error", "responde_con": "problema técnico"},
    {"nombre": "presupuesto agotado", "mensajes": ["Mi pedido RP-1002 llegó frío y quiero registrar un reclamo"],
     "agente": "reclamos", "reclamos": 0, "presupuesto": 1, "stop_reason": "limite"},
]
