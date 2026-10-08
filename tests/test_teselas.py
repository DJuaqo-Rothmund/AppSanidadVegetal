import io
import threading

import pytest

from sanidad.geo import teselas as t

PREDIO = (-72.50, -39.56, -72.44, -39.53)  # caja aproximada de El Amanecer


def test_tesela_de_coordenadas_conocidas():
    assert t.lonlat_a_tesela(0, 0, 1) == (1, 1)
    assert t.lonlat_a_tesela(-180, 85, 2) == (0, 0)
    assert t.lonlat_a_tesela(179.99, -85, 2) == (3, 3)


@pytest.mark.parametrize("z", [5, 13, 19])
def test_ida_y_vuelta(z):
    x, y = t.lonlat_a_tesela(-72.47, -39.54, z)
    lng, lat = t.tesela_a_lonlat(x, y, z)  # esquina noroeste
    assert t.lonlat_a_tesela(lng + 1e-9, lat - 1e-9, z) == (x, y)


def test_xyz_a_tms():
    assert t.xyz_a_tms(0, 3) == 7
    assert t.xyz_a_tms(7, 3) == 0


def test_caja_con_margen_en_metros():
    min_lng, min_lat, max_lng, max_lat = t.caja_con_margen((-72.5, -39.5, -72.5, -39.5), 1000)
    assert (max_lat - min_lat) * 111_195 == pytest.approx(2000, rel=1e-3)
    assert (max_lng - min_lng) * 111_195 * 0.7716 == pytest.approx(2000, rel=2e-3)


@pytest.fixture
def almacen(tmp_path):
    a = t.AlmacenTeselas(tmp_path / "esri.mbtiles")
    yield a
    a.cerrar()


def test_almacen_guarda_en_esquema_tms(almacen):
    almacen.guardar(3, 2, 1, b"jpg")
    assert almacen.leer(3, 2, 1) == b"jpg"
    assert almacen.leer(3, 2, 6) is None
    fila = almacen._con.execute("SELECT tile_row FROM tiles").fetchone()[0]
    assert fila == 6  # 2**3 - 1 - 1
    assert almacen.existentes(3) == {(2, 1)}
    assert almacen.resumen() == {"teselas": 1, "bytes": 3, "zoom_min": 3, "zoom_max": 3}


def test_planificar_omite_lo_guardado_y_limita_el_zoom(almacen):
    plan = t.planificar(almacen, [PREDIO], 13, 25, margen_m=0)
    assert plan.zoom_max == 19  # zoom máximo nativo de ESRI
    assert plan.ya_guardadas == 0
    z, x, y = plan.pendientes[0]
    almacen.guardar(z, x, y, b"x")
    plan2 = t.planificar(almacen, [PREDIO], 13, 25, margen_m=0)
    assert plan2.ya_guardadas == 1 and len(plan2.pendientes) == len(plan.pendientes) - 1


def test_planificar_por_poligono_pide_menos_que_el_rectangulo(almacen):
    a = (-72.50, -39.56, -72.495, -39.555)
    b = (-72.445, -39.535, -72.44, -39.53)
    por_poligono = t.planificar(almacen, [a, b], 18, 18, margen_m=0)
    rectangulo = t.planificar(almacen, [(-72.50, -39.56, -72.44, -39.53)], 18, 18, margen_m=0)
    assert len(por_poligono.pendientes) < len(rectangulo.pendientes) / 5


def test_planificar_respeta_el_limite(almacen):
    with pytest.raises(ValueError, match="más de"):
        t.planificar(almacen, [PREDIO], 10, 19, limite=100)


def test_descargar_guarda_y_avanza(almacen):
    plan = t.planificar(almacen, [PREDIO], 12, 14, margen_m=0)
    avances = []
    avance = t.descargar(plan, almacen, lambda z, x, y: f"{z}/{x}/{y}".encode(),
                         al_avanzar=lambda a: avances.append(a.fraccion), hilos=2, lote=3)
    assert avance.terminado and not avance.cancelado
    assert avance.listas == plan.total and avance.fallidas == 0
    z, x, y = plan.pendientes[-1]
    assert almacen.leer(z, x, y) == f"{z}/{x}/{y}".encode()
    assert avances[-1] == 1.0


def test_descargar_corta_sin_senal(almacen):
    plan = t.planificar(almacen, [PREDIO], 16, 17, margen_m=0)

    def sin_senal(z, x, y):
        raise t.ErrorTesela("sin red")

    avance = t.descargar(plan, almacen, sin_senal, hilos=1, max_fallas_seguidas=5)
    assert avance.cancelado and avance.motivo_corte
    assert avance.fallidas < len(plan.pendientes)
    assert almacen.resumen()["teselas"] == 0


def test_descargar_cancelable(almacen):
    plan = t.planificar(almacen, [PREDIO], 16, 17, margen_m=0)
    cancelar = threading.Event()

    def obtener(z, x, y):
        cancelar.set()
        return b"x"

    avance = t.descargar(plan, almacen, obtener, cancelar=cancelar, hilos=1)
    assert avance.cancelado and avance.listas < plan.total


class Resp:
    def __init__(self, estado, tipo="image/jpeg", contenido=b"jpg"):
        self.status_code = estado
        self.headers = {"Content-Type": tipo}
        self.content = contenido

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))


class Http:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_cliente_esri_usa_orden_z_y_x():
    http = Http(Resp(200))
    assert t.ClienteTeselas(http=http).obtener(15, 100, 200) == b"jpg"
    assert http.urls[0].endswith("/World_Imagery/MapServer/tile/15/200/100")


def test_cliente_reintenta_errores_de_red_pero_no_los_permanentes(monkeypatch):
    import requests
    monkeypatch.setattr(t.time, "sleep", lambda s: None)
    http = Http(requests.ConnectionError("x"), Resp(200))
    assert t.ClienteTeselas(http=http).obtener(1, 0, 0) == b"jpg"
    with pytest.raises(t.ErrorTesela, match="404"):
        t.ClienteTeselas(http=Http(Resp(404))).obtener(1, 0, 0)
    with pytest.raises(t.ErrorTesela, match="no es una imagen"):
        t.ClienteTeselas(http=Http(Resp(200, tipo="text/html"))).obtener(1, 0, 0)


def _jpeg(color):
    from PIL import Image
    salida = io.BytesIO()
    Image.new("RGB", (256, 256), color).save(salida, "JPEG")
    return salida.getvalue()


def test_sobrezoom_agranda_el_cuadrante_correcto(almacen):
    from PIL import Image
    # Ancestro z=10 con cuadrantes de colores; el hijo (x*2+1, y*2) es el NE (verde).
    im = Image.new("RGB", (256, 256))
    for (cx, cy), color in {(0, 0): "red", (1, 0): "green", (0, 1): "blue", (1, 1): "white"}.items():
        im.paste(color, (cx * 128, cy * 128, cx * 128 + 128, cy * 128 + 128))
    salida = io.BytesIO()
    im.save(salida, "JPEG", quality=95)
    almacen.guardar(10, 300, 600, salida.getvalue())

    datos = t.leer_o_sobrezoom(almacen, 11, 601, 1200)
    hijo = Image.open(io.BytesIO(datos))
    r, g, b = hijo.getpixel((128, 128))
    assert hijo.size == (256, 256) and g > 100 and r < 80 and b < 80

    nieto = Image.open(io.BytesIO(t.sobrezoom(almacen, 12, 1203, 2400)))
    assert nieto.getpixel((128, 128))[1] > 100  # sigue en el cuadrante verde


def test_sobrezoom_sin_ancestro(almacen):
    almacen.guardar(5, 0, 0, _jpeg("red"))
    assert t.sobrezoom(almacen, 12, 0, 0, max_niveles=4) is None
    assert t.leer_o_sobrezoom(almacen, 5, 0, 0) is not None
