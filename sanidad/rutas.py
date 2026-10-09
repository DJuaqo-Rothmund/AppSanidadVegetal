"""Rutas de los archivos de datos empaquetados con la app."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"

CATALOGO = DATOS / "catalogo-frambuesa-v1.json"
SECTORES = DATOS / "sectores-el-amanecer.json"
MODELO_MOBILENET = RAIZ / "assets" / "modelos" / "mobilenet_v3_small.npz"
