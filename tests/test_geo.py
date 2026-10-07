import pytest

from sanidad.geo import Proyeccion, caja_total, punto_en_poligono, sector_en, sectores_desde_geojson

# Coordenadas sintéticas de prueba (no son del predio).
CUADRADO = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
CON_HUECO = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]]


@pytest.mark.parametrize("x, y, esperado", [
    (5, 5, True), (0.1, 9.9, True), (-1, 5, False), (11, 5, False), (5, 10.5, False),
])
def test_punto_en_cuadrado(x, y, esperado):
    assert punto_en_poligono(x, y, CUADRADO) is esperado


def test_hueco_queda_fuera():
    assert punto_en_poligono(5, 5, CON_HUECO) is False
    assert punto_en_poligono(2, 2, CON_HUECO) is True


def test_poligono_concavo():
    # Forma de "U": el centro superior queda fuera.
    u = [[(0, 0), (9, 0), (9, 9), (6, 9), (6, 3), (3, 3), (3, 9), (0, 9), (0, 0)]]
    assert punto_en_poligono(4.5, 6, u) is False
    assert punto_en_poligono(1.5, 6, u) is True
    assert punto_en_poligono(4.5, 1, u) is True


GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "id": "s1-e1-a",
         "properties": {"equipo": 1, "sector": 1, "variedad": "Meeker", "ha": "4.2"},
         "geometry": {"type": "Polygon", "coordinates": [
             [[-72.60, -39.10], [-72.59, -39.10], [-72.59, -39.09], [-72.60, -39.09], [-72.60, -39.10]]]}},
        {"type": "Feature",
         "properties": {"id": "s2-e1", "equipo": "1", "sector": "2"},
         "geometry": {"type": "MultiPolygon", "coordinates": [
             [[[-72.58, -39.10], [-72.57, -39.10], [-72.57, -39.09], [-72.58, -39.09], [-72.58, -39.10]]],
             [[[-72.56, -39.10], [-72.55, -39.10], [-72.55, -39.09], [-72.56, -39.09], [-72.56, -39.10]]]]}},
    ],
}


def test_sectores_desde_geojson():
    s1, s2 = sectores_desde_geojson(GEOJSON)
    assert (s1.id, s1.equipo, s1.sector, s1.variedad, s1.ha) == ("s1-e1-a", "1", "1", "Meeker", 4.2)
    assert s1.etiqueta == "S1 · E1"
    assert s2.id == "s2-e1" and len(s2.poligonos) == 2


def test_sector_en_deduce_el_sector():
    sectores = sectores_desde_geojson(GEOJSON)
    assert sector_en(sectores, -39.095, -72.595).id == "s1-e1-a"
    assert sector_en(sectores, -39.095, -72.555).id == "s2-e1"  # segunda parte no contigua
    assert sector_en(sectores, -39.095, -72.565) is None  # entre las dos partes


def test_caja_total():
    assert caja_total(sectores_desde_geojson(GEOJSON)) == (-72.60, -39.10, -72.55, -39.09)


def test_geometria_no_admitida():
    malo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0]}}]}
    with pytest.raises(ValueError, match="Point"):
        sectores_desde_geojson(malo)
    with pytest.raises(ValueError):
        sectores_desde_geojson({"type": "Feature"})


def test_proyeccion_conserva_proporcion_y_orientacion():
    p = Proyeccion((-72.60, -39.10, -72.55, -39.09), ancho=400, alto=400, margen=0)
    x0, y0 = p.a_pantalla(-72.60, -39.10)
    x1, y1 = p.a_pantalla(-72.55, -39.09)
    assert x1 > x0 and y1 > y0  # este a la derecha, norte arriba (Kivy crece hacia arriba)
    assert x1 - x0 == pytest.approx(400)  # el lado largo llena el ancho
    # 0,05° de longitud a -39° miden ~3,9 veces 0,01° de latitud
    assert (x1 - x0) / (y1 - y0) == pytest.approx(5 * 0.7765, rel=1e-3)


def test_proyeccion_ida_y_vuelta():
    p = Proyeccion((-72.60, -39.10, -72.55, -39.09), ancho=390, alto=600)
    lng, lat = p.a_geo(*p.a_pantalla(-72.575, -39.093))
    assert (lng, lat) == (pytest.approx(-72.575), pytest.approx(-39.093))


def test_sectores_empaquetados_de_el_amanecer():
    from sanidad import rutas
    from sanidad.geo import cargar_sectores

    sectores = cargar_sectores(rutas.SECTORES)
    assert len(sectores) == 62  # polígonos (partes no contiguas separadas)
    assert len({s.propiedades["sector_id"] for s in sectores}) == 40
    assert {s.equipo for s in sectores} == {"1", "2", "3", "4"}
    assert sum(s.ha for s in sectores) == pytest.approx(196.3, abs=0.2)
    min_lng, min_lat, max_lng, max_lat = caja_total(sectores)
    assert -73 < min_lng < max_lng < -72 and -40 < min_lat < max_lat < -39
    assert sector_en(sectores, -33.45, -70.66) is None  # Santiago queda fuera del predio


def test_variedades_de_el_amanecer():
    from collections import Counter

    from sanidad import rutas
    from sanidad.geo import cargar_sectores

    sectores = cargar_sectores(rutas.SECTORES)
    assert Counter(s.variedad for s in sectores) == {"Wakefield": 58, None: 4}
    s1e1 = [s for s in sectores if s.propiedades["sector_id"] == "E1-S1"]
    assert len(s1e1) == 4 and all(s.variedad is None for s in s1e1)
    assert all(s.propiedades["variedades_sector"] == ["Meeker", "Cascade Harvest"] for s in s1e1)
