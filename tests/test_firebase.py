import json

import pytest
import requests

from sanidad.config import RAIZ_PROYECTO, ConfiguracionFaltante, cargar_config
from sanidad.firebase import ClienteAuth, ClienteFirestore, ErrorFirebase, Sesion, SinConexion
from sanidad.firebase.firestore import a_campos, desde_campos


class Respuesta:
    def __init__(self, estado, cuerpo):
        self.status_code = estado
        self._cuerpo = cuerpo
        self.content = json.dumps(cuerpo).encode()

    def json(self):
        return self._cuerpo


class HttpFalso:
    """Imita requests.Session: devuelve respuestas en orden y guarda las llamadas."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def _responder(self, **llamada):
        self.llamadas.append(llamada)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def post(self, url, **kw):
        return self._responder(metodo="POST", url=url, **kw)

    def request(self, metodo, url, **kw):
        return self._responder(metodo=metodo, url=url, **kw)


# --- Authentication -----------------------------------------------------------

def test_iniciar_sesion_ok():
    http = HttpFalso(Respuesta(200, {
        "localId": "uid1", "email": "monitor@x.cl", "idToken": "tok",
        "refreshToken": "ref", "expiresIn": "3600",
    }))
    auth = ClienteAuth("KEY", http=http, reloj=lambda: 1000.0)
    s = auth.iniciar_sesion(" monitor@x.cl ", "secreta")
    assert s == Sesion("uid1", "monitor@x.cl", "tok", "ref", 4600.0)
    llamada = http.llamadas[0]
    assert "signInWithPassword" in llamada["url"]
    assert llamada["params"] == {"key": "KEY"}
    assert llamada["json"]["email"] == "monitor@x.cl"
    assert llamada["json"]["returnSecureToken"] is True


@pytest.mark.parametrize("mensaje_api, esperado", [
    ("INVALID_LOGIN_CREDENTIALS", "Correo o contraseña incorrectos."),
    ("TOO_MANY_ATTEMPTS_TRY_LATER : Access disabled", "Demasiados intentos. Espera unos minutos."),
    ("USER_DISABLED", "Esta cuenta está desactivada. Habla con el administrador."),
])
def test_errores_de_inicio_en_espanol(mensaje_api, esperado):
    http = HttpFalso(Respuesta(400, {"error": {"code": 400, "message": mensaje_api}}))
    with pytest.raises(ErrorFirebase) as e:
        ClienteAuth("KEY", http=http).iniciar_sesion("a@b.cl", "x")
    assert e.value.mensaje == esperado


def test_datos_incompletos_no_llaman_a_la_red():
    http = HttpFalso()
    with pytest.raises(ErrorFirebase) as e:
        ClienteAuth("KEY", http=http).iniciar_sesion("", "x")
    assert e.value.codigo == "DATOS_INCOMPLETOS"
    assert http.llamadas == []


def test_sin_conexion():
    http = HttpFalso(requests.ConnectionError("sin red"))
    with pytest.raises(SinConexion) as e:
        ClienteAuth("KEY", http=http).iniciar_sesion("a@b.cl", "x")
    assert "Sin conexión" in e.value.mensaje


def test_renovar_token():
    http = HttpFalso(Respuesta(200, {
        "user_id": "uid1", "id_token": "tok2", "refresh_token": "ref2", "expires_in": "3600",
    }))
    auth = ClienteAuth("KEY", http=http, reloj=lambda: 5000.0)
    s = auth.renovar(Sesion("uid1", "m@x.cl", "tok", "ref", 4600.0))
    assert (s.id_token, s.refresh_token, s.expira_en, s.email) == ("tok2", "ref2", 8600.0, "m@x.cl")
    assert http.llamadas[0]["data"]["grant_type"] == "refresh_token"


def test_renovar_con_token_revocado():
    http = HttpFalso(Respuesta(400, {"error": {"code": 400, "message": "INVALID_REFRESH_TOKEN"}}))
    with pytest.raises(ErrorFirebase) as e:
        ClienteAuth("KEY", http=http).renovar(Sesion("u", "m", "t", "r", 0))
    assert "venció" in e.value.mensaje


def test_necesita_renovar():
    s = Sesion("u", "m", "t", "r", expira_en=1000.0)
    assert not ClienteAuth("K", reloj=lambda: 800.0).necesita_renovar(s)
    assert ClienteAuth("K", reloj=lambda: 900.0).necesita_renovar(s)


def test_sesion_se_guarda_como_dict():
    s = Sesion("u", "m", "t", "r", 1.5)
    assert Sesion.desde_dict(json.loads(json.dumps(s.a_dict()))) == s


# --- Firestore ----------------------------------------------------------------

def test_conversion_de_valores_ida_y_vuelta():
    datos = {
        "nombre": "El Amanecer", "ha": 196.0, "hileras": 40, "activo": True, "nota": None,
        "miembros": {"uid1": "admin"}, "sectores": ["s1", "s2"],
        "valores": {"lista": [1, 2.5, {"a": False}]},
    }
    campos = a_campos(datos)
    assert campos["hileras"] == {"integerValue": "40"}
    assert campos["activo"] == {"booleanValue": True}
    assert desde_campos(campos) == datos


def test_tipo_no_admitido():
    with pytest.raises(TypeError):
        a_campos({"x": object()})


def doc(ruta, campos):
    return {"name": f"projects/p/databases/(default)/documents/{ruta}", "fields": a_campos(campos)}


def test_obtener_documento():
    http = HttpFalso(Respuesta(200, doc("predios/el-amanecer", {"nombre": "El Amanecer"})))
    fs = ClienteFirestore("p", token=lambda: "TOK", http=http)
    assert fs.obtener("predios/el-amanecer") == {"id": "el-amanecer", "nombre": "El Amanecer"}
    llamada = http.llamadas[0]
    assert llamada["metodo"] == "GET"
    assert llamada["url"].endswith("/projects/p/databases/(default)/documents/predios/el-amanecer")
    assert llamada["headers"]["Authorization"] == "Bearer TOK"


def test_obtener_inexistente_devuelve_none():
    http = HttpFalso(Respuesta(404, {"error": {"code": 404, "status": "NOT_FOUND"}}))
    assert ClienteFirestore("p", lambda: "T", http=http).obtener("predios/x") is None


def test_permiso_denegado():
    http = HttpFalso(Respuesta(403, {"error": {"code": 403, "message": "Missing or insufficient permissions.",
                                               "status": "PERMISSION_DENIED"}}))
    with pytest.raises(ErrorFirebase) as e:
        ClienteFirestore("p", lambda: "T", http=http).obtener("predios/x")
    assert e.value.codigo == "PERMISSION_DENIED"


def test_guardar_documento_sin_id_en_campos():
    http = HttpFalso(Respuesta(200, doc("predios/a/puntos/u1", {"tipo": "fijo"})))
    fs = ClienteFirestore("p", lambda: "T", http=http)
    assert fs.guardar("predios/a/puntos/u1", {"id": "u1", "tipo": "fijo"})["id"] == "u1"
    llamada = http.llamadas[0]
    assert llamada["metodo"] == "PATCH"
    assert llamada["json"] == {"fields": {"tipo": {"stringValue": "fijo"}}}


def test_listar_recorre_paginas():
    http = HttpFalso(
        Respuesta(200, {"documents": [doc("temporadas/t1", {})], "nextPageToken": "sig"}),
        Respuesta(200, {"documents": [doc("temporadas/t2", {})]}),
    )
    docs = ClienteFirestore("p", lambda: "T", http=http).listar("temporadas")
    assert [d["id"] for d in docs] == ["t1", "t2"]
    assert http.llamadas[1]["params"]["pageToken"] == "sig"


def test_actualizados_desde_arma_la_consulta():
    http = HttpFalso(Respuesta(200, [
        {"document": doc("predios/a/observaciones/o1", {"actualizadoEn": "2026-10-07T12:00:01.000Z"})},
        {"readTime": "2026-10-07T12:00:02Z"},
    ]))
    fs = ClienteFirestore("p", lambda: "T", http=http)
    docs = fs.actualizados_desde("predios/a/observaciones", "2026-10-07T12:00:00.000Z")
    assert [d["id"] for d in docs] == ["o1"]
    llamada = http.llamadas[0]
    assert llamada["url"].endswith("/documents/predios/a:runQuery")
    q = llamada["json"]["structuredQuery"]
    assert q["from"] == [{"collectionId": "observaciones"}]
    assert q["where"]["fieldFilter"]["op"] == "GREATER_THAN"


def test_actualizados_desde_en_coleccion_raiz():
    http = HttpFalso(Respuesta(200, []))
    ClienteFirestore("p", lambda: "T", http=http).actualizados_desde("temporadas", "2026")
    assert http.llamadas[0]["url"].endswith("/documents:runQuery")


@pytest.mark.parametrize("metodo, ruta", [
    ("obtener", "predios"), ("obtener", "predios/a/puntos"), ("listar", "predios/a"),
    ("obtener", "predios//x"),
])
def test_rutas_invalidas(metodo, ruta):
    fs = ClienteFirestore("p", lambda: "T", http=HttpFalso())
    with pytest.raises(ValueError):
        getattr(fs, metodo)(ruta)


# --- configuración ------------------------------------------------------------

def test_config_falta_archivo(tmp_path):
    with pytest.raises(ConfiguracionFaltante, match="firebase_config.example.json"):
        cargar_config([tmp_path])


def test_config_plantilla_sin_completar(tmp_path):
    (tmp_path / "firebase_config.json").write_text(
        (RAIZ_PROYECTO / "firebase_config.example.json").read_text())
    with pytest.raises(ConfiguracionFaltante, match="apiKey"):
        cargar_config([tmp_path])


def test_config_ok(tmp_path):
    (tmp_path / "firebase_config.json").write_text(json.dumps({"apiKey": "A", "projectId": "P"}))
    assert cargar_config([tmp_path / "otra", tmp_path])["projectId"] == "P"
