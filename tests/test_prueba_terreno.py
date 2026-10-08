import csv

from sanidad import prueba_terreno as pt
from sanidad.geo import sectores_desde_geojson, ubicar

from .test_geo import GEOJSON


def test_anotar_listar_y_exportar(base, tmp_path):
    sectores = sectores_desde_geojson(GEOJSON)
    dentro = ubicar(sectores, -39.095, -72.595, precision_m=4.2)
    fuera = ubicar(sectores, -39.095, -72.585, precision_m=8)
    p1 = pt.anotar(base, dentro, "poste norte", reloj=lambda: "2026-10-08T12:00:00.000Z")
    p2 = pt.anotar(base, fuera)
    assert (p1["n"], p1["sector"], p1["equipo"], p1["variedad"]) == (1, "1", "1", "Meeker")
    assert p1["en_borde"] is False and p1["nota"] == "poste norte"
    assert p2["n"] == 2 and p2["sector"] is None and p2["fuera_cerca_de"]
    assert len(pt.listar(base)) == 2

    ruta = pt.exportar_csv(base, tmp_path / "puntos.csv")
    filas = list(csv.DictReader(open(ruta, encoding="utf-8"), delimiter=";"))
    assert [f["n"] for f in filas] == ["1", "2"]
    assert filas[0]["precision_m"] == "4.2" and filas[0]["en_borde"] == "no"

    pt.borrar_todos(base)
    assert pt.listar(base) == []
