"""Puntos de prueba en terreno (etapa 2): el sector deducido por GPS vs. el plano.

Cada punto guarda la coordenada, la precisión, el sector deducido y la
distancia al borde. Se exportan a CSV para revisarlos contra el plano.
Se guardan en los ajustes locales: no es parte del modelo de Firestore.
"""

import csv

from .db import ahora_iso

CLAVE = "puntos_prueba"
COLUMNAS = ["n", "fecha_hora", "lat", "lng", "precision_m", "sector_id", "sector", "equipo",
            "variedad", "distancia_borde_m", "en_borde", "fuera_cerca_de", "nota"]


def _fila(n, u, nota, momento):
    s = u.sector
    return {
        "n": n,
        "fecha_hora": momento,
        "lat": round(u.lat, 7),
        "lng": round(u.lng, 7),
        "precision_m": None if u.precision_m is None else round(u.precision_m, 1),
        "sector_id": s.propiedades.get("sector_id", s.id) if s else None,
        "sector": s.sector if s else None,
        "equipo": s.equipo if s else None,
        "variedad": (s.variedad or " / ".join(s.propiedades.get("variedades_sector") or [])) if s else None,
        "distancia_borde_m": None if u.distancia_borde_m is None else round(u.distancia_borde_m, 1),
        "en_borde": u.en_borde,
        "fuera_cerca_de": u.cercano.etiqueta if u.cercano else None,
        "nota": nota or "",
    }


def anotar(base, ubicacion, nota=None, reloj=ahora_iso):
    puntos = listar(base)
    fila = _fila(len(puntos) + 1, ubicacion, nota, reloj())
    puntos.append(fila)
    base.guardar_ajuste(CLAVE, puntos)
    return fila


def listar(base):
    return base.leer_ajuste(CLAVE, [])


def borrar_todos(base):
    base.borrar_ajuste(CLAVE)


def exportar_csv(base, ruta):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, delimiter=";")
        w.writeheader()
        for fila in listar(base):
            w.writerow({**fila, "en_borde": "sí" if fila["en_borde"] else "no"})
    return ruta
