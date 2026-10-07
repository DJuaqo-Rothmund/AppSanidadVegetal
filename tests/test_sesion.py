import pytest

from sanidad.firebase import ErrorFirebase, Sesion, SinConexion
from sanidad.sesion import GestorSesion


class AuthFalso:
    def __init__(self, ahora=0.0, renovar_lanza=None):
        self.ahora = ahora
        self.renovar_lanza = renovar_lanza
        self.renovaciones = 0

    def iniciar_sesion(self, email, contrasena):
        if contrasena != "ok":
            raise ErrorFirebase("INVALID_LOGIN_CREDENTIALS")
        return Sesion("uid1", email, "tok1", "ref1", self.ahora + 3600)

    def renovar(self, s):
        if self.renovar_lanza:
            raise self.renovar_lanza
        self.renovaciones += 1
        return Sesion(s.uid, s.email, f"tok{self.renovaciones + 1}", "ref", self.ahora + 3600)

    def necesita_renovar(self, s):
        return self.ahora >= s.expira_en - 120


def test_inicia_y_recuerda_la_sesion(base):
    g = GestorSesion(base, AuthFalso())
    assert not g.activa
    g.iniciar("m@x.cl", "ok")
    otra_apertura = GestorSesion(base, AuthFalso())
    assert otra_apertura.activa and otra_apertura.sesion.uid == "uid1"


def test_credenciales_malas_no_guardan_nada(base):
    g = GestorSesion(base, AuthFalso())
    with pytest.raises(ErrorFirebase):
        g.iniciar("m@x.cl", "mala")
    assert not g.activa and base.leer_ajuste("sesion") is None


def test_token_vigente_no_renueva(base):
    auth = AuthFalso()
    g = GestorSesion(base, auth)
    g.iniciar("m@x.cl", "ok")
    assert g.token() == "tok1" and auth.renovaciones == 0


def test_token_por_vencer_se_renueva_y_guarda(base):
    auth = AuthFalso()
    g = GestorSesion(base, auth)
    g.iniciar("m@x.cl", "ok")
    auth.ahora = 3500
    assert g.token() == "tok2"
    assert base.leer_ajuste("sesion")["id_token"] == "tok2"


def test_sin_senal_usa_el_token_actual(base):
    auth = AuthFalso()
    g = GestorSesion(base, auth)
    g.iniciar("m@x.cl", "ok")
    auth.ahora, auth.renovar_lanza = 9999, SinConexion()
    assert g.token() == "tok1" and g.activa


def test_token_revocado_cierra_la_sesion(base):
    auth = AuthFalso()
    g = GestorSesion(base, auth)
    g.iniciar("m@x.cl", "ok")
    auth.ahora, auth.renovar_lanza = 9999, ErrorFirebase("INVALID_REFRESH_TOKEN")
    with pytest.raises(ErrorFirebase):
        g.token()
    assert not g.activa and base.leer_ajuste("sesion") is None


def test_token_sin_sesion(base):
    with pytest.raises(ErrorFirebase):
        GestorSesion(base, AuthFalso()).token()


def test_pendientes_por_subir(base, predio_id):
    g = GestorSesion(base, AuthFalso())
    assert g.pendientes_por_subir() == 1
    base.insertar("puntos", {"predio_id": predio_id, "tipo": "fijo", "lat": 0, "lng": 0})
    assert g.pendientes_por_subir() == 2


def test_cerrar(base):
    g = GestorSesion(base, AuthFalso())
    g.iniciar("m@x.cl", "ok")
    g.cerrar()
    assert not g.activa and not GestorSesion(base, AuthFalso()).activa
