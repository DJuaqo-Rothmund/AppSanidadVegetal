"""Genera datos/sectores-el-amanecer.json desde el GeoJSON de sectorización (40 sectores).

Separa cada sector en sus partes no contiguas (un polígono por parte, 62 en
El Amanecer) y normaliza las propiedades al modelo de SPEC.md.

Los sectores sin variedad en el plano reciben la variedad por defecto
(en El Amanecer, todos salvo el Sector 1 · Equipo 1 son Wakefield).

Uso:
    python scripts/importar_sectores.py origen.geojson datos/sectores-el-amanecer.json \
        [--variedad-por-defecto Wakefield]
"""

import json
import math
import re
import string

RADIO_TIERRA_M = 6371008.8


def area_ha(anillo):
    """Área aproximada (proyección equirectangular local) de un anillo (lng, lat), en ha."""
    lat0 = math.radians(sum(p[1] for p in anillo) / len(anillo))
    xy = [(math.radians(lng) * math.cos(lat0) * RADIO_TIERRA_M, math.radians(lat) * RADIO_TIERRA_M)
          for lng, lat, *_ in anillo]
    s = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(xy, xy[1:] + xy[:1]))
    return abs(s) / 2 / 10000


def numero(texto):
    m = re.search(r"\d+", str(texto or ""))
    return m.group(0) if m else None


def convertir(origen, variedad_por_defecto=None):
    salida = []
    for f in origen["features"]:
        p = f["properties"]
        g = f["geometry"]
        partes = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        variedades = [v.strip() for v in (p.get("variedades") or "").split(",") if v.strip()]
        if not variedades and variedad_por_defecto:
            variedades = [variedad_por_defecto]
        areas = [area_ha(parte[0]) - sum(area_ha(h) for h in parte[1:]) for parte in partes]
        for i, (parte, area) in enumerate(zip(partes, areas)):
            sufijo = string.ascii_lowercase[i] if len(partes) > 1 else ""
            salida.append({
                "type": "Feature",
                "id": f"{p['id']}{'-' + sufijo if sufijo else ''}",
                "properties": {
                    "sector_id": p["id"],
                    "nombre": p.get("nombre"),
                    "equipo": numero(p.get("equipo_riego")) or str(p.get("equipo_id")),
                    "sector": numero(p.get("sector")),
                    # Variedad por polígono: solo se conoce si el sector tiene una sola.
                    "variedad": variedades[0] if len(variedades) == 1 else None,
                    "variedades_sector": variedades,
                    "parte": i + 1,
                    "partes": len(partes),
                    "ha": round(area, 2),
                    "ha_sector": p.get("hectareas"),
                    "hileras_sector": p.get("hileras"),
                    "etiquetas_plano": p.get("etiquetas_plano"),
                    "color": p.get("color"),
                },
                "geometry": {"type": "Polygon", "coordinates": parte},
            })
    return {
        "type": "FeatureCollection",
        "name": "El Amanecer · sectores (un polígono por parte)",
        "origen": origen.get("name"),
        "features": salida,
    }


if __name__ == "__main__":
    import argparse

    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("origen")
    args.add_argument("destino")
    args.add_argument("--variedad-por-defecto", default=None)
    a = args.parse_args()
    with open(a.origen, encoding="utf-8") as f:
        resultado = convertir(json.load(f), a.variedad_por_defecto)
    with open(a.destino, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(resultado['features'])} polígonos escritos en {a.destino}")
