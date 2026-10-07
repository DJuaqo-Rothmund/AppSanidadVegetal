"""Geometría en Python puro: sectores desde GeoJSON y punto-en-polígono.

Coordenadas GeoJSON en orden (lng, lat). Sin librerías nativas, para no
complicar la compilación con Buildozer.
"""

import json
import math
from dataclasses import dataclass, field


@dataclass
class Sector:
    id: str
    equipo: str = None
    sector: str = None
    variedad: str = None
    ha: float = None
    propiedades: dict = field(default_factory=dict)
    # Lista de polígonos; cada uno es [anillo exterior, huecos...]; cada anillo [(lng, lat), ...]
    poligonos: list = field(default_factory=list)

    @property
    def etiqueta(self):
        partes = [f"S{self.sector}" if self.sector else None, f"E{self.equipo}" if self.equipo else None]
        return " · ".join(p for p in partes if p) or self.id

    def contiene(self, lng, lat):
        return any(punto_en_poligono(lng, lat, p) for p in self.poligonos)

    def caja(self):
        return caja([pt for p in self.poligonos for pt in p[0]])


def punto_en_anillo(x, y, anillo):
    """Regla par-impar (ray casting). Los puntos sobre el borde pueden caer a cualquier lado."""
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def punto_en_poligono(x, y, poligono):
    """Polígono GeoJSON: [exterior, hueco1, ...]. Dentro del exterior y fuera de los huecos."""
    if not poligono or not punto_en_anillo(x, y, poligono[0]):
        return False
    return not any(punto_en_anillo(x, y, hueco) for hueco in poligono[1:])


def caja(puntos):
    """(min_lng, min_lat, max_lng, max_lat) de una lista de puntos."""
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    return min(xs), min(ys), max(xs), max(ys)


def _texto(v):
    return None if v is None else str(v)


def sectores_desde_geojson(geojson):
    """Convierte una FeatureCollection en sectores. Acepta Polygon y MultiPolygon."""
    if isinstance(geojson, str):
        geojson = json.loads(geojson)
    if geojson.get("type") != "FeatureCollection":
        raise ValueError("Se esperaba un GeoJSON FeatureCollection")
    sectores = []
    for i, f in enumerate(geojson["features"]):
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            poligonos = [g["coordinates"]]
        elif g.get("type") == "MultiPolygon":
            poligonos = list(g["coordinates"])
        else:
            raise ValueError(f"Elemento {i}: geometría no admitida {g.get('type')!r}")
        p = f.get("properties") or {}
        ha = p.get("ha")
        sectores.append(Sector(
            id=_texto(f.get("id") or p.get("id") or i),
            equipo=_texto(p.get("equipo")),
            sector=_texto(p.get("sector")),
            variedad=p.get("variedad"),
            ha=float(ha) if ha is not None else None,
            propiedades=p,
            poligonos=poligonos,
        ))
    return sectores


def cargar_sectores(ruta):
    with open(ruta, encoding="utf-8") as f:
        return sectores_desde_geojson(json.load(f))


def sector_en(sectores, lat, lng):
    """Primer sector que contiene el punto, o None si cae fuera del predio."""
    for s in sectores:
        if s.contiene(lng, lat):
            return s
    return None


def caja_total(sectores):
    cajas = [s.caja() for s in sectores]
    return (min(c[0] for c in cajas), min(c[1] for c in cajas),
            max(c[2] for c in cajas), max(c[3] for c in cajas))


class Proyeccion:
    """Proyección equirectangular local de (lng, lat) a píxeles, para el mapa esquemático.

    Corrige la longitud por cos(latitud) para que el predio no se vea estirado,
    y ajusta la caja al rectángulo de pantalla conservando la proporción.
    """

    def __init__(self, caja_geo, ancho, alto, margen=16):
        min_lng, min_lat, max_lng, max_lat = caja_geo
        self.k = math.cos(math.radians((min_lat + max_lat) / 2))
        self.x0, self.y0 = min_lng * self.k, min_lat
        ancho_geo = max((max_lng - min_lng) * self.k, 1e-12)
        alto_geo = max(max_lat - min_lat, 1e-12)
        self.escala = min((ancho - 2 * margen) / ancho_geo, (alto - 2 * margen) / alto_geo)
        self.dx = (ancho - ancho_geo * self.escala) / 2
        self.dy = (alto - alto_geo * self.escala) / 2

    def a_pantalla(self, lng, lat):
        return (self.dx + (lng * self.k - self.x0) * self.escala,
                self.dy + (lat - self.y0) * self.escala)

    def a_geo(self, x, y):
        """Inversa de a_pantalla: de píxeles a (lng, lat)."""
        return ((x - self.dx) / self.escala + self.x0) / self.k, (y - self.dy) / self.escala + self.y0
