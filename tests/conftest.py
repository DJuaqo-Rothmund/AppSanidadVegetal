import itertools
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sanidad.db import BaseLocal  # noqa: E402


@pytest.fixture
def reloj():
    """Reloj falso que avanza un segundo en cada lectura."""
    contador = itertools.count()
    return lambda: f"2026-10-07T12:00:{next(contador):02d}.000Z"


@pytest.fixture
def base(reloj):
    b = BaseLocal(":memory:", reloj=reloj)
    yield b
    b.cerrar()


@pytest.fixture
def predio_id(base):
    return base.insertar("predios", {"nombre": "El Amanecer", "cultivo": "frambuesa"}, uid="u1")
