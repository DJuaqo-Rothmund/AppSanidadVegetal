"""Lee la configuración de Firebase desde firebase_config.json (fuera del repositorio)."""

import json
from pathlib import Path

NOMBRE_ARCHIVO = "firebase_config.json"
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
CLAVES_OBLIGATORIAS = ("apiKey", "projectId")


class ConfiguracionFaltante(Exception):
    pass


def cargar_config(carpetas=None):
    """Busca firebase_config.json en las carpetas dadas (por defecto, la raíz del proyecto)."""
    carpetas = [Path(c) for c in (carpetas or [RAIZ_PROYECTO])]
    for carpeta in carpetas:
        ruta = carpeta / NOMBRE_ARCHIVO
        if ruta.is_file():
            with open(ruta, encoding="utf-8") as f:
                config = json.load(f)
            faltan = [c for c in CLAVES_OBLIGATORIAS
                      if not config.get(c) or str(config[c]).startswith("PEGAR-AQUI")]
            if faltan:
                raise ConfiguracionFaltante(f"{ruta} no tiene: {', '.join(faltan)}")
            return config
    raise ConfiguracionFaltante(
        f"No se encontró {NOMBRE_ARCHIVO}. Copia firebase_config.example.json "
        f"como {NOMBRE_ARCHIVO} y completa apiKey y projectId."
    )
