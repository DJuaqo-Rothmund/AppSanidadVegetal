"""Teselas satelitales para usar el mapa sin señal (Web Mercator, esquema XYZ).

Adaptado de PuntoRiesgo (geo/tile_math.py y geo/tile_cache.py):

* matemática de teselas (lon/lat ↔ x/y/z),
* almacén MBTiles (SQLite estándar, filas en esquema TMS),
* plan de descarga: solo las teselas que tocan cada sector más un margen,
* descarga en paralelo, cancelable y reanudable,
* sobrezoom: si falta una tesela, se recorta y agranda la de un zoom menor.

Sin Kivy, para probarlo con pytest. Pillow solo se usa en el sobrezoom.

Nota: la descarga masiva y el uso sin señal de ESRI World Imagery están
sujetos a los términos de Esri.
"""

import io
import math
import sqlite3
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

import requests

RADIO_TIERRA_M = 6371008.8
LAT_MAX = 85.05112878

ESRI = {
    "id": "esri_world_imagery",
    "nombre": "ESRI World Imagery",
    # Ojo: ESRI usa el orden {z}/{y}/{x}.
    "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "atribucion": "Imágenes © Esri, Maxar, Earthstar Geographics",
    "zoom_max_nativo": 19,
}
USER_AGENT = "SanidadElAmanecer/0.2 (monitoreo sanitario, uso sin señal)"
BYTES_POR_TESELA = 25_000  # JPEG satelital de 256 px, promedio aproximado


# --- matemática de teselas ----------------------------------------------------

def lonlat_a_tesela(lng, lat, z):
    lat = max(min(lat, LAT_MAX), -LAT_MAX)
    n = 2 ** z
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tesela_a_lonlat(x, y, z):
    """Esquina noroeste (lng, lat) de la tesela."""
    n = 2 ** z
    lng = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lng, lat


def xyz_a_tms(y, z):
    """MBTiles guarda las filas en esquema TMS (origen abajo)."""
    return (2 ** z - 1) - y


def caja_con_margen(caja, metros):
    """Agranda una caja (min_lng, min_lat, max_lng, max_lat) en `metros` por lado."""
    min_lng, min_lat, max_lng, max_lat = caja
    dlat = math.degrees(metros / RADIO_TIERRA_M)
    lat_media = math.radians((min_lat + max_lat) / 2)
    dlng = math.degrees(metros / (RADIO_TIERRA_M * max(math.cos(lat_media), 1e-6)))
    return (max(min_lng - dlng, -180.0), max(min_lat - dlat, -LAT_MAX),
            min(max_lng + dlng, 180.0), min(max_lat + dlat, LAT_MAX))


def teselas_de_caja(caja, z):
    min_lng, min_lat, max_lng, max_lat = caja
    x0, y0 = lonlat_a_tesela(min_lng, max_lat, z)
    x1, y1 = lonlat_a_tesela(max_lng, min_lat, z)
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


# --- almacén MBTiles ----------------------------------------------------------

class AlmacenTeselas:
    """Archivo MBTiles, seguro entre hilos. Las coordenadas de la API son XYZ."""

    def __init__(self, ruta, fuente=ESRI):
        self.ruta = str(ruta)
        self._candado = threading.RLock()
        self._con = sqlite3.connect(self.ruta, check_same_thread=False)
        with self._candado:
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS tiles (
                    zoom_level  INTEGER NOT NULL,
                    tile_column INTEGER NOT NULL,
                    tile_row    INTEGER NOT NULL,
                    tile_data   BLOB    NOT NULL,
                    PRIMARY KEY (zoom_level, tile_column, tile_row)
                );
            """)
            self._con.executemany(
                "INSERT OR REPLACE INTO metadata(name, value) VALUES (?, ?)",
                [("name", fuente["nombre"]), ("format", "jpg"), ("type", "baselayer"),
                 ("attribution", fuente["atribucion"]), ("scheme", "tms")],
            )
            self._con.commit()

    def leer(self, z, x, y):
        with self._candado:
            fila = self._con.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, xyz_a_tms(y, z)),
            ).fetchone()
        return bytes(fila[0]) if fila else None

    def guardar_varias(self, teselas):
        filas = [(z, x, xyz_a_tms(y, z), sqlite3.Binary(d)) for z, x, y, d in teselas]
        if not filas:
            return
        with self._candado:
            self._con.executemany(
                "INSERT OR REPLACE INTO tiles(zoom_level, tile_column, tile_row, tile_data) "
                "VALUES (?, ?, ?, ?)", filas)
            self._con.commit()

    def guardar(self, z, x, y, datos):
        self.guardar_varias([(z, x, y, datos)])

    def existentes(self, z):
        """(x, y) XYZ guardadas en el zoom z (para reanudar una descarga)."""
        with self._candado:
            filas = self._con.execute(
                "SELECT tile_column, tile_row FROM tiles WHERE zoom_level=?", (z,)).fetchall()
        return {(x, (2 ** z - 1) - fila) for x, fila in filas}

    def resumen(self):
        with self._candado:
            cantidad, bytes_ = self._con.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(tile_data)), 0) FROM tiles").fetchone()
            zmin, zmax = self._con.execute(
                "SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles").fetchone()
        return {"teselas": cantidad, "bytes": bytes_, "zoom_min": zmin, "zoom_max": zmax}

    def cerrar(self):
        with self._candado:
            self._con.close()


# --- plan y descarga ----------------------------------------------------------

@dataclass
class PlanDescarga:
    zoom_min: int
    zoom_max: int
    pendientes: list
    ya_guardadas: int = 0

    @property
    def total(self):
        return len(self.pendientes) + self.ya_guardadas

    @property
    def megas_estimados(self):
        return len(self.pendientes) * BYTES_POR_TESELA / 1_048_576


def planificar(almacen, cajas, zoom_min, zoom_max, margen_m=250, fuente=ESRI, limite=60_000):
    """Teselas que tocan cada caja (con margen); omite las ya guardadas.

    Con una caja por polígono, en los zooms altos solo se piden las teselas
    que tocan sectores reales y no todo el rectángulo del predio.
    """
    if zoom_min > zoom_max:
        raise ValueError("zoom_min mayor que zoom_max")
    zoom_max = min(zoom_max, fuente["zoom_max_nativo"])
    cajas = [caja_con_margen(c, margen_m) for c in cajas]
    pendientes, ya = [], 0
    for z in range(zoom_min, zoom_max + 1):
        buscadas = set()
        for c in cajas:
            buscadas |= teselas_de_caja(c, z)
        if len(buscadas) + len(pendientes) + ya > limite:
            raise ValueError(f"El área necesita más de {limite} teselas hasta el zoom {z}")
        tiene = almacen.existentes(z)
        ya += len(buscadas & tiene)
        pendientes.extend((z, x, y) for x, y in sorted(buscadas - tiene))
    return PlanDescarga(zoom_min, zoom_max, pendientes, ya)


class ErrorTesela(Exception):
    pass


class ClienteTeselas:
    """Descarga una tesela de la fuente (por defecto ESRI)."""

    def __init__(self, fuente=ESRI, http=None, tiempo_espera_s=10, reintentos=2):
        self.fuente = fuente
        self.http = http or requests.Session()
        self.tiempo_espera_s = tiempo_espera_s
        self.reintentos = reintentos

    def obtener(self, z, x, y):
        url = self.fuente["url"].format(z=z, x=x, y=y)
        ultimo = None
        for intento in range(self.reintentos + 1):
            try:
                r = self.http.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.tiempo_espera_s)
                if r.status_code in (400, 401, 403, 404):
                    raise ErrorTesela(f"{z}/{x}/{y}: HTTP {r.status_code}")
                r.raise_for_status()
                if not r.headers.get("Content-Type", "").startswith("image/") or not r.content:
                    raise ErrorTesela(f"{z}/{x}/{y}: la respuesta no es una imagen")
                return r.content
            except ErrorTesela:
                raise
            except requests.RequestException as e:
                ultimo = e
                if intento < self.reintentos:
                    time.sleep(0.5 * 2 ** intento)
        raise ErrorTesela(f"{z}/{x}/{y}: {ultimo}")


@dataclass
class Avance:
    total: int
    listas: int = 0
    fallidas: int = 0
    bytes: int = 0
    terminado: bool = False
    cancelado: bool = False
    motivo_corte: str = None
    errores: list = field(default_factory=list)

    @property
    def fraccion(self):
        return 1.0 if self.total == 0 else (self.listas + self.fallidas) / self.total


def descargar(plan, almacen, obtener, al_avanzar=None, cancelar=None, hilos=4,
              max_fallas_seguidas=20, lote=64):
    """Descarga el plan (bloqueante: llamar desde un hilo). Devuelve el Avance final.

    Si fallan `max_fallas_seguidas` teselas seguidas (se perdió la señal),
    corta la descarga; como es reanudable, basta volver a planificar.
    """
    cancelar = cancelar or threading.Event()
    avance = Avance(total=plan.total, listas=plan.ya_guardadas)
    pendientes = iter(plan.pendientes)
    buffer, seguidas = [], 0

    with ThreadPoolExecutor(max_workers=max(1, hilos)) as pool:
        en_curso = {}
        for t in pendientes:
            en_curso[pool.submit(obtener, *t)] = t
            if len(en_curso) >= hilos * 4:
                break
        while en_curso:
            hechas, _ = wait(en_curso, return_when=FIRST_COMPLETED)
            for futuro in hechas:
                z, x, y = en_curso.pop(futuro)
                try:
                    datos = futuro.result()
                    buffer.append((z, x, y, datos))
                    avance.listas += 1
                    avance.bytes += len(datos)
                    seguidas = 0
                except Exception as e:  # noqa: BLE001 - se informa y se sigue
                    avance.fallidas += 1
                    seguidas += 1
                    if len(avance.errores) < 10:
                        avance.errores.append(str(e))
                    if seguidas >= max_fallas_seguidas and not avance.motivo_corte:
                        avance.motivo_corte = "Se perdió la conexión con el servidor de mapas."
                        cancelar.set()
                if not cancelar.is_set():
                    siguiente = next(pendientes, None)
                    if siguiente is not None:
                        en_curso[pool.submit(obtener, *siguiente)] = siguiente
            if len(buffer) >= lote:
                almacen.guardar_varias(buffer)
                buffer.clear()
            if al_avanzar:
                al_avanzar(avance)
    almacen.guardar_varias(buffer)
    avance.cancelado = cancelar.is_set()
    avance.terminado = True
    if al_avanzar:
        al_avanzar(avance)
    return avance


# --- sobrezoom ----------------------------------------------------------------

def sobrezoom(almacen, z, x, y, max_niveles=4, tam=256):
    """Genera la tesela z/x/y recortando y agrandando un ancestro guardado.

    Devuelve JPEG en bytes, o None si no hay ancestro en `max_niveles` zooms.
    """
    for d in range(1, max_niveles + 1):
        if z - d < 0:
            break
        datos = almacen.leer(z - d, x >> d, y >> d)
        if datos is None:
            continue
        from PIL import Image  # solo aquí, para no exigir Pillow en el resto

        lado = tam >> d  # píxeles del ancestro que cubren esta tesela
        ox = (x - ((x >> d) << d)) * lado
        oy = (y - ((y >> d) << d)) * lado
        with Image.open(io.BytesIO(datos)) as im:
            im = im.convert("RGB")
            if im.size != (tam, tam):
                im = im.resize((tam, tam))
            recorte = im.crop((ox, oy, ox + max(lado, 1), oy + max(lado, 1)))
            salida = io.BytesIO()
            recorte.resize((tam, tam), Image.BILINEAR).save(salida, "JPEG", quality=85)
            return salida.getvalue()
    return None


def leer_o_sobrezoom(almacen, z, x, y, max_niveles=4):
    """La tesela guardada o, si no está, una sobreampliada desde un ancestro."""
    return almacen.leer(z, x, y) or sobrezoom(almacen, z, x, y, max_niveles)
