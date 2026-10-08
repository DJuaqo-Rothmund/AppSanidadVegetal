"""Mapa satelital (ESRI) con kivy_garden.mapview, sectores y ubicación GPS.

Las teselas salen primero del MBTiles local; si no están y hay señal se
descargan y se guardan; sin señal se arma un sobrezoom desde un zoom menor.
"""

import io
import math
import time

from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as EtiquetaCore
from kivy.graphics import Color, Ellipse, Line, Mesh, PopMatrix, PushMatrix, Rectangle, Scale, Translate
from kivy.graphics.tesselator import TYPE_POLYGONS, WINDING_ODD, Tesselator
from kivy.metrics import dp, sp
from kivy.properties import ObjectProperty
from kivy_garden.mapview import MapLayer, MapSource, MapView
from kivy_garden.mapview.downloader import Downloader

from ..geo import teselas
from .tema import COLOR

ZOOM_MIN = 12
ZOOM_MAX = 20  # ESRI llega a 19; el 20 sale por sobrezoom
PAUSA_SIN_RED_S = 30


class FuenteSatelital(MapSource):
    def __init__(self, almacen, cliente, cache_dir, **kwargs):
        super().__init__(
            url=teselas.ESRI["url"], cache_key="esri", min_zoom=ZOOM_MIN, max_zoom=ZOOM_MAX,
            tile_size=256, image_ext="jpg", attribution=teselas.ESRI["atribucion"],
            cache_dir=cache_dir, **kwargs)
        self.almacen = almacen
        self.cliente = cliente
        self._sin_red_hasta = 0.0

    def fill_tile(self, tile):
        if tile.state == "done":
            return
        Downloader.instance(self.cache_dir).submit(self._cargar, tile)

    def _cargar(self, tile):
        z, x = tile.zoom, tile.tile_x
        y = (2 ** z - 1) - tile.tile_y  # mapview numera las filas como TMS
        datos = self.almacen.leer(z, x, y)
        if datos is None and z <= teselas.ESRI["zoom_max_nativo"] and time.time() >= self._sin_red_hasta:
            try:
                datos = self.cliente.obtener(z, x, y)
                self.almacen.guardar(z, x, y, datos)
            except Exception:  # noqa: BLE001 - sin señal: se sigue con lo guardado
                self._sin_red_hasta = time.time() + PAUSA_SIN_RED_S
        if datos is None:
            datos = teselas.sobrezoom(self.almacen, z, x, y, max_niveles=5)
        if datos is None:
            tile.state = "done"
            return None
        imagen = CoreImage(io.BytesIO(datos), ext="jpg", filename=f"{z}.{x}.{y}.jpg")
        return self._lista, (tile, imagen)

    @staticmethod
    def _lista(tile, imagen):
        tile.texture = imagen.texture
        tile.state = "need-animation"


class CapaSectores(MapLayer):
    """Polígonos de los sectores. Se teselan una vez por zoom y se mueven con una matriz."""

    sectores = ObjectProperty([])
    seleccionado = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._zoom_cache = None
        self._mundo = []  # [(sector, [anillos en píxeles del mundo])]
        self._texturas = {}
        self.bind(sectores=self._invalidar, seleccionado=lambda *a: self.reposition())

    def _invalidar(self, *_):
        self._zoom_cache = None
        self.reposition()

    def _proyectar(self, zoom):
        fuente = self.parent.map_source
        self._mundo = [
            (s, [[[fuente.get_x(zoom, p[0]), fuente.get_y(zoom, p[1])] for p in anillo]
                 for anillo in poligono])
            for s in self.sectores for poligono in s.poligonos
        ]
        self._zoom_cache = zoom

    def reposition(self):
        vista = self.parent
        if vista is None:
            return
        zoom = vista.zoom
        if self._zoom_cache != zoom:
            self._proyectar(zoom)
        vx, vy = vista.viewport_pos
        escala = vista.scale
        self.canvas.clear()
        with self.canvas:
            PushMatrix()
            Translate(vista.x, vista.y)
            Scale(escala, escala, 1)
            Translate(-vx, -vy)
            ancho = dp(1.2) / escala
            for sector, anillos in self._mundo:
                activo = sector is self.seleccionado
                planos = [[c for p in anillo for c in p] for anillo in anillos]
                if activo:
                    Color(*COLOR["accion"][:3], 0.30)
                    tess = Tesselator()
                    for plano in planos:
                        tess.add_contour(plano)
                    if tess.tesselate(WINDING_ODD, TYPE_POLYGONS):
                        for vertices, indices in tess.meshes:
                            Mesh(vertices=vertices, indices=indices, mode="triangle_fan")
                Color(*(COLOR["accion"] if activo else (1, 1, 0.55, 0.9)))
                for plano in planos:
                    Line(points=plano, close=True, width=ancho * (2 if activo else 1))
            PopMatrix()
            self._etiquetas(vista, escala, vx, vy)

    def _etiquetas(self, vista, escala, vx, vy):
        if vista.zoom < 16:
            return
        # Una etiqueta por sector, en su primera parte.
        vistos = set()
        for sector, anillos in self._mundo:
            clave = sector.propiedades.get("sector_id", sector.id)
            if clave in vistos:
                continue
            vistos.add(clave)
            xs = [p[0] for p in anillos[0]]
            ys = [p[1] for p in anillos[0]]
            cx = vista.x + ((min(xs) + max(xs)) / 2 - vx) * escala
            cy = vista.y + ((min(ys) + max(ys)) / 2 - vy) * escala
            tx = self._texturas.get(sector.etiqueta)
            if tx is None:
                etiqueta = EtiquetaCore(text=sector.etiqueta, font_size=sp(11), bold=True,
                                        color=(1, 1, 1, 1), outline_width=2, outline_color=(0, 0, 0))
                etiqueta.refresh()
                tx = self._texturas[sector.etiqueta] = etiqueta.texture
            Color(1, 1, 1, 1)
            Rectangle(texture=tx, size=tx.size, pos=(cx - tx.width / 2, cy - tx.height / 2))


class CapaUbicacion(MapLayer):
    """Punto azul con el círculo de precisión del GPS."""

    ubicacion = ObjectProperty(None, allownone=True)  # (lat, lng, precision_m)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(ubicacion=lambda *a: self.reposition())

    def reposition(self):
        vista = self.parent
        self.canvas.clear()
        if vista is None or self.ubicacion is None:
            return
        lat, lng, precision = self.ubicacion
        x, y = vista.get_window_xy_from(lat, lng, vista.zoom)
        with self.canvas:
            if precision:
                m_por_px = m_por_px_mundo(lat, vista.zoom, vista.map_source.dp_tile_size) / vista.scale
                r = max(precision / m_por_px, dp(8))
                Color(*COLOR["ubicacion"][:3], 0.18)
                Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))
                Color(*COLOR["ubicacion"][:3], 0.6)
                Line(circle=(x, y, r), width=dp(1))
            Color(1, 1, 1, 1)
            Ellipse(pos=(x - dp(9), y - dp(9)), size=(dp(18), dp(18)))
            Color(*COLOR["ubicacion"])
            Ellipse(pos=(x - dp(6.5), y - dp(6.5)), size=(dp(13), dp(13)))


def m_por_px_mundo(lat, zoom, tam_tesela):
    """Metros por píxel del mapa en ese zoom y latitud (tesela de `tam_tesela` px)."""
    return 40075016.686 * math.cos(math.radians(lat)) / (2 ** zoom) / tam_tesela


class MapaSatelital(MapView):
    """MapView que avisa un toque corto (sin arrastrar) con su lat/lng."""

    __events__ = ("on_toque",)

    def on_touch_up(self, touch):
        if (touch.grab_current is self and self._touch_count == 1
                and math.hypot(touch.x - touch.ox, touch.y - touch.oy) < dp(10)):
            c = self.get_latlon_at(touch.x - self.x, touch.y - self.y)
            self.dispatch("on_toque", c.lat, c.lon)
        return super().on_touch_up(touch)

    def on_toque(self, lat, lng):
        pass
