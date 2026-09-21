"""
Fase 11 — Ejercicio 3: tools seguras (idempotencia, circuit breaker y métricas)
===============================================================================
El agente falla y REINTENTA (fase 8: reintentos del cliente, tool caída, hilos que se reanudan).
Eso es bueno... hasta que la tool tiene efectos reales. Este ejercicio blinda las tools:

  1. IDEMPOTENCIA — si `crear_reclamo` se ejecuta dos veces con lo mismo (reintento de red, el
     modelo repite la llamada, se reanuda un hilo), debe crear UN solo reclamo. Se logra con una
     CLAVE que identifica la operación ("pedido + motivo normalizado") y un registro de lo ya hecho.
     Trampa: solo se guarda si la tool TERMINÓ BIEN. Si falló, guardar el fallo impediría reintentar.

  2. CIRCUIT BREAKER — si una tool falla seguido, seguir llamándola gasta tiempo y tokens del
     modelo en reintentos inútiles. Tras `umbral` fallos SEGUIDOS el circuito se ABRE: durante
     `enfriamiento` segundos ni se intenta y se responde un error inmediato. Pasado ese tiempo se
     deja pasar UNA llamada de prueba: si sale bien se cierra; si falla, se reabre.

  3. MÉTRICAS — sin números no sabes qué tool falla ni cuánto tarda: llamadas, fallos, tasa de
     fallo y latencia por tool. Las llamadas bloqueadas por el breaker no cuentan (no se ejecutaron).

Todo se prueba sin API y sin esperar de verdad: el reloj se inyecta (`reloj`), así que el test
adelanta el tiempo a mano. Es la misma técnica de "inyectar la dependencia" de la fase 10.

Ejecutar (desde la raíz del repo):
    python ejercicios/fase_11/ejercicio_3.py
"""

import sys
import time


# ------------------------------------------------------------------ 1. idempotencia
class EjecutorIdempotente:
    def __init__(self):
        self.resultados = {}  # clave → resultado de la primera ejecución exitosa

    def ejecutar(self, clave: str, funcion) -> dict:
        if ___BLANK_1___:
            return {**self.resultados[clave], "repetido": True}
        resultado = funcion()  # si lanza, NO se guarda nada: el reintento podrá ejecutarse
        ___BLANK_2___
        return {**resultado, "repetido": False}


RECLAMOS = []


def _crear_reclamo(pedido_id: str, motivo: str) -> dict:
    RECLAMOS.append({"id": f"REC-{len(RECLAMOS) + 1}", "pedido": pedido_id, "motivo": motivo})
    return RECLAMOS[-1]


def crear_reclamo(idem: EjecutorIdempotente, pedido_id: str, motivo: str) -> dict:
    # Misma operación = mismo pedido y mismo motivo, sin importar mayúsculas ni espacios sobrantes.
    clave = f"{pedido_id}:{___BLANK_3___}"
    return idem.ejecutar(clave, lambda: _crear_reclamo(pedido_id, motivo))


# ------------------------------------------------------------------ 2. circuit breaker
class CircuitBreaker:
    def __init__(self, umbral=3, enfriamiento=30.0, reloj=time.monotonic):
        self.umbral = umbral
        self.enfriamiento = enfriamiento
        self.reloj = reloj
        self.fallos = 0  # fallos SEGUIDOS
        self.abierto_desde = None  # None = cerrado

    def permitir(self) -> bool:
        if self.abierto_desde is None:
            return True
        # Abierto: solo se deja pasar la llamada de prueba cuando terminó el enfriamiento.
        return ___BLANK_4___

    def exito(self) -> None:
        ___BLANK_5___
        self.abierto_desde = None

    def fallo(self) -> None:
        self.fallos += 1
        if ___BLANK_6___:
            self.abierto_desde = self.reloj()


# ------------------------------------------------------------------ 3. métricas
class Metricas:
    def __init__(self):
        self.datos = {}

    def registrar(self, tool: str, segundos: float, ok: bool) -> None:
        d = self.datos.setdefault(tool, {"llamadas": 0, "fallos": 0, "segundos": []})
        d["llamadas"] += 1
        d["fallos"] += ___BLANK_7___
        d["segundos"].append(segundos)

    def resumen(self) -> dict:
        return {
            tool: {
                "llamadas": d["llamadas"],
                "fallos": d["fallos"],
                "tasa_fallo": ___BLANK_8___,
                "latencia_max": max(d["segundos"]),
            }
            for tool, d in self.datos.items()
        }


# ------------------------------------------------------------------ ensamble
class EjecutorSeguro:
    """Todas las llamadas a tools pasan por aquí: breaker por tool + métricas."""

    def __init__(self, reloj=time.monotonic, umbral=3, enfriamiento=30.0):
        self.reloj = reloj
        self.umbral = umbral
        self.enfriamiento = enfriamiento
        self.metricas = Metricas()
        self.breakers = {}

    def ejecutar(self, nombre: str, funcion, **args) -> dict:
        """Devuelve siempre un dict tipo tool_result: {"is_error": bool, "content": str}."""
        breaker = self.breakers.setdefault(nombre, CircuitBreaker(self.umbral, self.enfriamiento, self.reloj))
        if ___BLANK_9___:
            return {"is_error": True, "content": f"{nombre} está temporalmente fuera de servicio; no reintentes ahora"}
        inicio = self.reloj()
        try:
            resultado = funcion(**args)
        except Exception as e:
            self.metricas.registrar(nombre, self.reloj() - inicio, ok=False)
            breaker.fallo()
            return {"is_error": True, "content": f"{nombre} falló: {e}"}
        self.metricas.registrar(nombre, self.reloj() - inicio, ok=True)
        ___BLANK_10___
        return {"is_error": False, "content": str(resultado)}


class RelojFalso:
    """Reloj controlado por el test: nada de esperar de verdad."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def main() -> int:
    fallos = 0

    def chequear(nombre, condicion):
        nonlocal fallos
        print(f"  {'✓' if condicion else '✗'} {nombre}")
        fallos += 0 if condicion else 1

    print("Idempotencia de crear_reclamo:")
    idem = EjecutorIdempotente()
    a = crear_reclamo(idem, "RP-1002", "llegó frío")
    b = crear_reclamo(idem, "RP-1002", "llegó frío")
    chequear("el reintento NO crea un segundo reclamo", len(RECLAMOS) == 1)
    chequear("el reintento devuelve el mismo reclamo, marcado como repetido", a["id"] == b["id"] and b["repetido"] and not a["repetido"])
    crear_reclamo(idem, "RP-1002", "  LLEGÓ FRÍO ")
    chequear("mayúsculas y espacios no cambian la operación", len(RECLAMOS) == 1)
    crear_reclamo(idem, "RP-1002", "faltó una bebida")
    chequear("otro motivo SÍ es otra operación", len(RECLAMOS) == 2)
    idem2, intentos = EjecutorIdempotente(), []

    def inestable():
        intentos.append(1)
        if len(intentos) == 1:
            raise TimeoutError("sin respuesta")
        return {"id": "REC-X"}

    try:
        idem2.ejecutar("k", inestable)
    except TimeoutError:
        pass
    chequear("un fallo NO se guarda: el reintento se ejecuta", idem2.ejecutar("k", inestable)["id"] == "REC-X" and len(intentos) == 2)

    print("Circuit breaker (con reloj falso):")
    reloj = RelojFalso()
    cb = CircuitBreaker(umbral=3, enfriamiento=30.0, reloj=reloj)
    for _ in range(3):
        cb.fallo()
    chequear("tras 3 fallos seguidos se abre", not cb.permitir())
    reloj.t = 29
    chequear("a los 29 s sigue abierto", not cb.permitir())
    reloj.t = 30
    chequear("a los 30 s deja pasar la llamada de prueba", cb.permitir())
    cb.fallo()
    chequear("si la prueba falla, se reabre", not cb.permitir())
    reloj.t = 60
    cb.exito()
    chequear("si la prueba sale bien, se cierra", cb.permitir() and cb.fallos == 0)
    cb2 = CircuitBreaker(umbral=3, reloj=reloj)
    cb2.fallo(), cb2.fallo(), cb2.exito(), cb2.fallo(), cb2.fallo()
    chequear("un éxito reinicia la cuenta: fallos NO seguidos no abren", cb2.permitir())

    print("EjecutorSeguro (breaker + métricas juntos):")
    reloj = RelojFalso()
    seguro, llamadas = EjecutorSeguro(reloj=reloj, umbral=3, enfriamiento=30.0), []

    def tool_caida(**_):
        llamadas.append(1)
        reloj.t += 2
        raise ConnectionError("timeout")

    def tool_sana(x):
        reloj.t += 0.5
        return f"ok {x}"

    respuestas = [seguro.ejecutar("estado_pedido", tool_caida, pedido="RP-9999") for _ in range(4)]
    chequear("las 3 primeras llamadas intentan y fallan", len(llamadas) == 3 and all(r["is_error"] for r in respuestas[:3]))
    chequear("la 4.ª NO llama a la tool (circuito abierto)", len(llamadas) == 3 and "fuera de servicio" in respuestas[3]["content"])
    chequear("otra tool no se ve afectada", seguro.ejecutar("consultar_pago", tool_sana, x=1) == {"is_error": False, "content": "ok 1"})
    resumen = seguro.metricas.resumen()
    chequear("métricas: 3 llamadas, 3 fallos, tasa 1.0 (la bloqueada no cuenta)",
             resumen["estado_pedido"]["llamadas"] == 3 and resumen["estado_pedido"]["tasa_fallo"] == 1.0)
    chequear("métricas: latencia máxima medida con el reloj (2 s)", resumen["estado_pedido"]["latencia_max"] == 2)
    chequear("métricas: la tool sana tiene tasa 0.0", resumen["consultar_pago"]["tasa_fallo"] == 0.0)
    reloj.t += 30
    chequear("pasado el enfriamiento vuelve a intentar", seguro.ejecutar("estado_pedido", tool_caida)["is_error"] and len(llamadas) == 4)

    print(f"\nResultado: {'OK' if fallos == 0 else f'{fallos} chequeos fallaron'}")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
