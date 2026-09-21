"""Estado del grafo. Con memoria por hilo el estado vive ENTRE mensajes, así que cada campo
necesita una política explícita:

  ACUMULAN (reducer)         historial, traza, tokens_usados
  SE REINICIAN por turno     traspasos, aprobado (los pone en 0/False el supervisor;
                             `aprobado` es fail-closed: una aprobación jamás vale para el turno siguiente)
  SE SOBREESCRIBEN           mensaje, agente, respuesta, stop_reason, user_id
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class Estado(TypedDict, total=False):
    mensaje: str
    user_id: str
    agente: str
    historial: Annotated[list, operator.add]
    stop_reason: str
    respuesta: str
    traza: Annotated[list, operator.add]
    traspasos: int
    aprobado: bool
    tokens_usados: Annotated[int, operator.add]
