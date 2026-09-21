"""python -m agent_harness.evals [--fake] [--repeticiones N] [--umbral X]   → exit 0 (listo) / 1 (no listo)

Sin --fake usa la API real (cuesta tokens). Con --fake usa FakeLLM: verifica la fontanería, no la calidad."""

import argparse
import sys

from dotenv import load_dotenv

from ..config import Settings
from ..testing import FakeLLM
from .runner import evaluar

load_dotenv()
p = argparse.ArgumentParser()
p.add_argument("--fake", action="store_true")
p.add_argument("--repeticiones", type=int, default=3)
p.add_argument("--umbral", type=float, default=0.8)
a = p.parse_args()
sys.exit(0 if evaluar(settings=Settings.from_env(), llm=FakeLLM() if a.fake else None,
                      repeticiones=a.repeticiones, umbral=a.umbral) else 1)
