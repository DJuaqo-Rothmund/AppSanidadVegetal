import importlib.util
from pathlib import Path

import numpy as np
import pytest

from sanidad import rutas
from sanidad.ia.mobilenet import MobileNet

RAIZ = Path(__file__).resolve().parent.parent


def _imagenes_de_prueba():
    spec = importlib.util.spec_from_file_location("exportar", RAIZ / "scripts" / "exportar_mobilenet.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.imagenes_de_prueba()


@pytest.fixture(scope="module")
def red():
    return MobileNet(rutas.MODELO_MOBILENET)


def test_numpy_igual_a_tensorflow(red):
    """La red en numpy reproduce la salida de TensorFlow (pesos en float16)."""
    esperado = np.load(RAIZ / "tests" / "datos" / "mobilenet_referencia.npz")["embeddings"]
    for imagen, e in zip(_imagenes_de_prueba(), esperado):
        y = red.embedding(imagen)
        assert y.shape == (576,)
        coseno = float(y @ e / np.linalg.norm(y) / np.linalg.norm(e))
        assert coseno > 0.9999
        assert np.abs(y - e).max() < 0.02 * np.abs(e).max()


def test_imagenes_distintas_dan_vectores_distintos(red):
    a, b, _ = _imagenes_de_prueba()
    ya, yb = red.embedding(a), red.embedding(b)
    assert float(ya @ yb / np.linalg.norm(ya) / np.linalg.norm(yb)) < 0.99
