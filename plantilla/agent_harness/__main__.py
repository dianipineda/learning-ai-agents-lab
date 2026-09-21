"""Chat de consola:  python -m agent_harness   ('nuevo' abre otra conversación, 'salir' termina)."""

import uuid

from dotenv import load_dotenv

from .app import crear_app
from .config import Settings
from .observability import configurar_logging


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    configurar_logging(settings.log_level)
    orq = crear_app(settings).orquestador

    def preguntar(acciones: list) -> bool:
        print("\n⏸  Acción pendiente de aprobación:")
        for a in acciones:
            print(f"   - {a['tool']}({a['argumentos']})")
        return input("¿Aprobar? (s/n): ").strip().lower() == "s"

    print("Agente — 'nuevo' otra conversación, 'salir' termina\n")
    thread_id = str(uuid.uuid4())
    while True:
        texto = input("Tú: ").strip()
        if texto.lower() == "salir":
            return
        if texto.lower() == "nuevo":
            thread_id = str(uuid.uuid4())
            print("\n(nueva conversación)\n")
            continue
        for ev in orq.eventos(thread_id, texto, preguntar):
            if ev["tipo"] == "progreso":
                print(f"  · {ev['tool']}…")
            elif ev["tipo"] == "final":
                e = ev["estado"]
                print(f"\nRuta: {' → '.join(e['traza'])}\nAgente: {e['respuesta']}\n")


if __name__ == "__main__":
    main()
