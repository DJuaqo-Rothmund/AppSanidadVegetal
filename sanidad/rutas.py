"""Rutas de los archivos de datos empaquetados con la app."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
FUENTES = RAIZ / "assets" / "fonts"

CATALOGO = DATOS / "catalogo-frambuesa-v1.json"
SECTORES = DATOS / "sectores-el-amanecer.json"
