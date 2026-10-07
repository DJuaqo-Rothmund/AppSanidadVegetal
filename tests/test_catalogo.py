import copy

import pytest

from sanidad import rutas
from sanidad.catalogo import Catalogo, CatalogoInvalido, cargar_catalogo, validar


@pytest.fixture(scope="module")
def catalogo():
    return cargar_catalogo(rutas.CATALOGO)


def test_catalogo_empaquetado_es_valido(catalogo):
    assert catalogo.id == "frambuesa-v1"
    assert validar(catalogo.datos) == []


def test_grupos_del_catalogo(catalogo):
    assert len(catalogo.por_grupo("enfermedad")) == 5
    assert len(catalogo.por_grupo("plaga")) == 5
    assert catalogo.organismo("zarzamora")["grupo"] == "maleza"


def test_umbral_simple_y_doble(catalogo):
    (u,) = catalogo.umbrales(catalogo.organismo("botrytis"))
    assert u["indicador"] == "incidencia"
    assert (u["cerca"]["valor"], u["sobre"]["valor"]) == (3, 5)
    dobles = catalogo.umbrales(catalogo.organismo("drosophila_suzukii"))
    assert [x["indicador"] for x in dobles] == ["capturas", "pct_frutos_con_larva"]


@pytest.mark.parametrize("bbch, esperado", [(None, True), (56, False), (57, True), (89, True), (90, False)])
def test_ventana_bbch(catalogo, bbch, esperado):
    assert Catalogo.en_ventana(catalogo.organismo("botrytis"), bbch) is esperado


def test_lista_rapida_deja_al_final_lo_fuera_de_ventana(catalogo):
    # BBCH 20: botrytis (57–89) y roya (31–95) quedan al final.
    ids = [o["id"] for o in catalogo.lista_rapida("enfermedad", 20)]
    assert ids[-2:] == ["botrytis", "roya"]
    assert set(ids) == {o["id"] for o in catalogo.por_grupo("enfermedad")}


def _base(catalogo):
    return copy.deepcopy(catalogo.datos)


@pytest.mark.parametrize("romper, mensaje", [
    (lambda d: d["organismos"][0].update(grupo="virus"), "grupo inválido"),
    (lambda d: d["organismos"][1].update(id=d["organismos"][0]["id"]), "id repetido"),
    (lambda d: d["organismos"][0]["indicadores"][0].update(numerador="no_existe"), "no es un campo"),
    (lambda d: d["organismos"][0]["umbral"]["sobre"].update(medida="x"), "que no existe"),
    (lambda d: d["organismos"][0].update(estados=[]), "no tiene estados"),
    (lambda d: d["organismos"][0].update(reglas_especiales=["magia"]), "regla especial sin definir"),
    (lambda d: d.pop("version"), "falta 'version'"),
])
def test_validar_detecta_errores(catalogo, romper, mensaje):
    d = _base(catalogo)
    romper(d)
    assert any(mensaje in e for e in validar(d))
    with pytest.raises(CatalogoInvalido):
        Catalogo(d)
