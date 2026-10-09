import sqlite3
import uuid

import pytest

from sanidad.db import BaseLocal
from sanidad.db.esquema import TABLAS, VERSION_ESQUEMA


def test_crea_todas_las_tablas_del_modelo(base):
    nombres = {f[0] for f in base.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLAS) | {"ajustes"} <= nombres
    assert base.con.execute("PRAGMA user_version").fetchone()[0] == VERSION_ESQUEMA


def test_cada_tabla_tiene_campos_de_auditoria(base):
    for tabla in TABLAS:
        cols = {f[1] for f in base.con.execute(f"PRAGMA table_info({tabla})")}
        assert {"id", "creado_en", "creado_por", "editado_en", "editado_por",
                "actualizado_en", "eliminado", "pendiente"} <= cols, tabla


def test_insertar_genera_uuid_y_auditoria(base, predio_id):
    p = base.obtener("predios", predio_id)
    assert uuid.UUID(p["id"]).version == 4
    assert p["creado_por"] == "u1"
    assert p["creado_en"] == p["actualizado_en"]
    assert p["pendiente"] == 1 and p["eliminado"] == 0


def test_columnas_json_ida_y_vuelta(base, predio_id):
    obs = base.insertar("observaciones", {
        "predio_id": predio_id, "organismo_id": "botrytis", "catalogo_version": "frambuesa-v1",
        "fecha_hora_telefono": "2026-10-07T12:00:00.000Z",
        "valores": {"n_evaluados": 100, "n_con_sintoma": 4},
        "clima": {"tempC": 18.5, "fuente": "api", "hojaMojada": True},
        "estados_biologicos": ["lesión"],
    })
    o = base.obtener("observaciones", obs)
    assert o["valores"] == {"n_evaluados": 100, "n_con_sintoma": 4}
    assert o["clima"]["hojaMojada"] is True
    assert o["estados_biologicos"] == ["lesión"]
    assert o["fotos"] is None


def test_actualizar_registra_edicion(base, predio_id):
    base.marcar_sincronizado("predios", predio_id, base.obtener("predios", predio_id)["actualizado_en"])
    base.actualizar("predios", predio_id, {"ha": 196}, uid="u2")
    p = base.obtener("predios", predio_id)
    assert p["ha"] == 196
    assert p["editado_por"] == "u2"
    assert p["actualizado_en"] > p["creado_en"]
    assert p["pendiente"] == 1


def test_anular_no_borra(base, predio_id):
    base.anular("predios", predio_id, uid="u2")
    assert base.listar("predios") == []
    ocultos = base.listar("predios", incluir_eliminados=True)
    assert len(ocultos) == 1 and ocultos[0]["eliminado"] == 1
    assert base.pendientes("predios")[0]["id"] == predio_id


def test_marcar_sincronizado_respeta_cambios_posteriores(base, predio_id):
    subido = base.obtener("predios", predio_id)["actualizado_en"]
    base.actualizar("predios", predio_id, {"ha": 10})  # cambió mientras se subía
    base.marcar_sincronizado("predios", predio_id, subido)
    assert base.obtener("predios", predio_id)["pendiente"] == 1
    base.marcar_sincronizado("predios", predio_id, base.obtener("predios", predio_id)["actualizado_en"])
    assert base.pendientes("predios") == []


def test_listar_con_filtros(base, predio_id):
    base.insertar("puntos", {"predio_id": predio_id, "tipo": "fijo", "lat": -39.0, "lng": -72.0})
    base.insertar("puntos", {"predio_id": predio_id, "tipo": "trampa", "lat": -39.1, "lng": -72.1})
    assert [p["tipo"] for p in base.listar("puntos", tipo="trampa")] == ["trampa"]


@pytest.mark.parametrize("tabla, datos", [
    ("no_existe", {}),
    ("predios", {"nombre": "x", "columna_falsa": 1}),
    ("predios", {"nombre": "x", "creado_por": "intruso"}),
    ("predios", {"nombre; DROP TABLE predios": 1}),
])
def test_rechaza_tablas_y_columnas_invalidas(base, tabla, datos):
    with pytest.raises(ValueError):
        base.insertar(tabla, datos)


def test_restricciones_del_esquema(base, predio_id):
    with pytest.raises(sqlite3.IntegrityError):
        base.insertar("puntos", {"predio_id": predio_id, "tipo": "otro", "lat": 0, "lng": 0})
    with pytest.raises(sqlite3.IntegrityError):
        base.insertar("sectores", {"predio_id": "predio-inexistente"})


def test_editar_registro_inexistente(base):
    with pytest.raises(KeyError):
        base.actualizar("predios", "no-existe", {"ha": 1})


def test_ajustes(base):
    assert base.leer_ajuste("sesion") is None
    base.guardar_ajuste("sesion", {"uid": "u1"})
    base.guardar_ajuste("sesion", {"uid": "u2"})
    assert base.leer_ajuste("sesion") == {"uid": "u2"}
    base.borrar_ajuste("sesion")
    assert base.leer_ajuste("sesion", "nada") == "nada"


def test_reabrir_archivo_conserva_datos(tmp_path):
    ruta = str(tmp_path / "sanidad.sqlite3")
    b = BaseLocal(ruta)
    pid = b.insertar("predios", {"nombre": "El Amanecer"})
    b.cerrar()
    b2 = BaseLocal(ruta)
    assert b2.obtener("predios", pid)["nombre"] == "El Amanecer"
    b2.cerrar()


def test_migra_una_base_de_la_version_1(tmp_path):
    """Un teléfono con la base de la etapa 1 recibe la tabla nueva sin perder datos."""
    ruta = str(tmp_path / "v1.sqlite3")
    b = BaseLocal(ruta)
    pid = b.insertar("predios", {"nombre": "El Amanecer"})
    b.con.execute("DROP TABLE referencias_ia")
    b.con.execute("PRAGMA user_version = 1")
    b.con.commit()
    b.cerrar()
    b2 = BaseLocal(ruta)
    assert b2.obtener("predios", pid)["nombre"] == "El Amanecer"
    assert b2.con.execute("PRAGMA user_version").fetchone()[0] == VERSION_ESQUEMA
    b2.insertar("referencias_ia", {"especie_id": "x", "grupo": "maleza", "vector": b"\x00\x00",
                                   "modelo": "m"})
    b2.cerrar()


def test_base_usable_desde_otros_hilos(base, predio_id):
    import threading
    errores = []

    def trabajo(n):
        try:
            for _ in range(20):
                base.insertar("puntos", {"predio_id": predio_id, "tipo": "fijo", "lat": n, "lng": n})
                base.listar("puntos")
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    hilos = [threading.Thread(target=trabajo, args=(i,)) for i in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == [] and len(base.listar("puntos")) == 80
