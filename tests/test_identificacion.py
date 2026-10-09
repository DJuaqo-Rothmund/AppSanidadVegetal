import json

import numpy as np
import pytest
from PIL import Image

from sanidad.catalogo import cargar_catalogo
from sanidad import rutas
from sanidad.ia.identificador import MODELO, Identificador, normalizar, preparar_imagen
from sanidad.ia.servicio import CatalogoEspecies, ServicioIdentificacion

# --- identificador (vectores sintéticos) ----------------------------------------


def _clusters(n_especies=4, por_especie=3, dim=576, ruido=0.05, semilla=0):
    rng = np.random.default_rng(semilla)
    centros = normalizar(rng.normal(size=(n_especies, dim)))
    vectores, especies, fotos = [], [], []
    for i, c in enumerate(centros):
        for j in range(por_especie):
            vectores.append(c + ruido * rng.normal(size=dim))
            especies.append(f"esp{i}")
            fotos.append(f"esp{i}_{j}")
    return centros, np.array(vectores), especies, fotos


def test_sugerir_ordena_por_parecido():
    centros, v, e, _ = _clusters()
    ident = Identificador(v, e)
    s = ident.sugerir(centros[2], k=3)
    assert [x.especie_id for x in s][0] == "esp2"
    assert len(s) == 3 and s[0].confianza > 0.9
    assert abs(sum(x.confianza for x in ident.sugerir(centros[2], k=4)) - 1) < 1e-6


def test_sugerir_respeta_especies_permitidas():
    centros, v, e, _ = _clusters()
    s = Identificador(v, e).sugerir(centros[2], permitidas={"esp0", "esp1"})
    assert {x.especie_id for x in s} <= {"esp0", "esp1"}


def test_identificador_vacio():
    assert Identificador().sugerir(np.ones(576)) == []


def test_agregar_referencia_cambia_la_sugerencia():
    centros, v, e, _ = _clusters()
    ident = Identificador(v, e)
    nuevo = normalizar(np.random.default_rng(9).normal(size=576))
    assert ident.sugerir(nuevo)[0].especie_id != "nueva"
    ident.agregar(nuevo, "nueva")
    assert ident.sugerir(nuevo)[0].especie_id == "nueva"


def test_evaluar_dejando_fuera_cada_foto():
    _, v, e, f = _clusters(ruido=0.02)
    r = Identificador(v, e).evaluar(f)
    assert r["fotos"] == 12 and r["top1"] == 100 and r["top3"] == 100


def test_preparar_imagen_recorta_cuadrado_y_espejo(tmp_path):
    im = Image.new("RGB", (400, 300), "white")
    im.paste((255, 0, 0), (0, 0, 200, 300))  # mitad izquierda roja
    ruta = tmp_path / "f.jpg"
    im.save(ruta)
    a = preparar_imagen(ruta)
    b = preparar_imagen(ruta, espejo=True)
    assert a.shape == (224, 224, 3) and a.dtype == np.uint8
    assert a[112, 5, 0] > 200 and a[112, 5, 1] < 60      # izquierda roja
    assert b[112, 218, 0] > 200 and b[112, 218, 1] < 60  # en el espejo queda a la derecha


# --- catálogo de especies ----------------------------------------------------------

MALEZAS = {"especies": [
    {"id": "rubus_ulmifolius", "familia": "ROSACEAE", "cientifico": "Rubus ulmifolius Schott",
     "nombres_comunes": ["ZARZAMORA", "MORA"], "fotos": ["rubus_ulmifolius_1.jpg"]},
    {"id": "rumex_acetosella", "familia": "POLYGONACEAE", "cientifico": "Rumex acetosella L.",
     "nombres_comunes": ["VINAGRILLO", "ROMACILLA"], "fotos": []},
    {"id": "taraxacum_officinale", "familia": "ASTERACEAE", "cientifico": "Taraxacum officinale",
     "nombres_comunes": ["DIENTE DE LEÓN"], "fotos": []},
]}


@pytest.fixture
def catalogo():
    return CatalogoEspecies(MALEZAS, cargar_catalogo(rutas.CATALOGO))


def test_catalogo_junta_malezas_y_organismos(catalogo):
    assert catalogo.ficha("rubus_ulmifolius")["grupo"] == "maleza"
    assert catalogo.ficha("botrytis")["grupo"] == "enfermedad"
    assert catalogo.ficha("drosophila_suzukii")["grupo"] == "plaga"
    # la zarzamora del catálogo de monitoreo es Rubus ulmifolius del libro: no se duplica
    assert catalogo.ficha("zarzamora") is None and catalogo.ficha("rubus_ulmifolius")


@pytest.mark.parametrize("texto, esperado", [
    ("diente de leon", "taraxacum_officinale"), ("ZARZA", "rubus_ulmifolius"),
    ("rumex", "rumex_acetosella"), ("polygonaceae", "rumex_acetosella"),
])
def test_buscar_sin_tildes(catalogo, texto, esperado):
    assert catalogo.buscar(texto, grupo="maleza")[0]["id"] == esperado


def test_nombre_visible(catalogo):
    assert CatalogoEspecies.nombre(catalogo.ficha("rubus_ulmifolius")) == "Zarzamora"


# --- servicio (red falsa: el vector depende del color medio) ------------------------


class RedFalsa:
    def embedding(self, imagen):
        v = np.zeros(576, dtype=np.float32)
        r, g, b = imagen.reshape(-1, 3).mean(axis=0) / 255
        v[0], v[1], v[2], v[3] = r, g, b, 0.1
        return v


def _foto(tmp_path, nombre, color):
    ruta = tmp_path / nombre
    Image.new("RGB", (300, 300), color).save(ruta)
    return ruta


def test_servicio_confirmar_y_volver_a_identificar(base, catalogo, tmp_path):
    libro = tmp_path / "ref.npz"
    v = normalizar(np.array([[1, 0, 0, .1] + [0] * 572, [0, 1, 0, .1] + [0] * 572], dtype=np.float32))
    np.savez(libro, vectores=v.astype(np.float16), especies=np.array(["rubus_ulmifolius", "rumex_acetosella"]),
             fotos=np.array(["a.jpg", "b.jpg"]), modelo=np.array(MODELO))
    srv = ServicioIdentificacion(base, catalogo, None, libro, tmp_path / "refs", cargar_red=RedFalsa)

    rojo = _foto(tmp_path, "rojo.jpg", (250, 10, 10))
    s, ficha = srv.identificar(rojo)[0]
    assert s.especie_id == "rubus_ulmifolius" and ficha["nombres_comunes"][0] == "ZARZAMORA"

    azul = _foto(tmp_path, "azul.jpg", (10, 10, 250))  # ninguna referencia azul todavía
    assert srv.identificar(azul)[0][0].especie_id != "taraxacum_officinale"
    srv.confirmar(azul, "taraxacum_officinale", uid="u1")
    assert srv.identificar(azul)[0][0].especie_id == "taraxacum_officinale"

    resumen = srv.resumen()
    assert resumen["fotos_libro"] == 2 and resumen["fotos_terreno"] == 1
    ref = srv.referencias_de("taraxacum_officinale")[0]
    assert ref["origen"] == "usuario" and ref["creado_por"] == "u1"

    # Otra apertura de la app: la referencia de terreno se recarga desde SQLite
    srv2 = ServicioIdentificacion(base, catalogo, None, libro, tmp_path / "refs", cargar_red=RedFalsa)
    assert srv2.identificar(azul)[0][0].especie_id == "taraxacum_officinale"

    srv2.quitar_referencia(ref["id"])
    assert srv2.identificar(azul)[0][0].especie_id != "taraxacum_officinale"


def test_servicio_filtra_por_grupo(base, catalogo, tmp_path):
    srv = ServicioIdentificacion(base, catalogo, None, None, None, cargar_red=RedFalsa)
    foto = _foto(tmp_path, "f.jpg", (100, 200, 50))
    srv.confirmar(foto, "botrytis")
    assert srv.identificar(foto, grupo="maleza") == []
    assert srv.identificar(foto, grupo="enfermedad")[0][0].especie_id == "botrytis"


def test_servicio_rechaza_especie_desconocida(base, catalogo, tmp_path):
    srv = ServicioIdentificacion(base, catalogo, None, None, None, cargar_red=RedFalsa)
    with pytest.raises(KeyError):
        srv.confirmar(_foto(tmp_path, "f.jpg", "red"), "no_existe")
