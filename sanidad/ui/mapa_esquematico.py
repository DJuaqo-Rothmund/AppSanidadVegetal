"""Mapa esquemático: dibuja los polígonos de los sectores sin teselas satelitales.

Es la vista de respaldo del mapa (SPEC.md) y la pantalla provisoria de la etapa 1.
Al tocar el mapa se resalta el sector tocado (punto-en-polígono).
"""

from kivy.core.text import Label as EtiquetaCore
from kivy.graphics import Color, Line, Mesh, Rectangle
from kivy.graphics.tesselator import TYPE_POLYGONS, WINDING_ODD, Tesselator
from kivy.metrics import dp, sp
from kivy.properties import ListProperty, ObjectProperty
from kivy.uix.widget import Widget

from ..geo import Proyeccion, caja_total, sector_en
from .tema import COLOR


class MapaEsquematico(Widget):
    sectores = ListProperty([])
    seleccionado = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.proyeccion = None
        self.bind(pos=self.redibujar, size=self.redibujar,
                  sectores=self.redibujar, seleccionado=self.redibujar)

    def redibujar(self, *_):
        self.canvas.clear()
        if not self.sectores or self.width < 10 or self.height < 10:
            self.proyeccion = None
            return
        self.proyeccion = Proyeccion(caja_total(self.sectores), self.width, self.height, margen=dp(16))
        with self.canvas:
            Color(*COLOR["mapa_fondo"])
            Rectangle(pos=self.pos, size=self.size)
            for s in self.sectores:
                activo = s is self.seleccionado
                for poligono in s.poligonos:
                    anillos = [self._a_pantalla(a) for a in poligono]
                    Color(*COLOR["sector_activo" if activo else "sector_relleno"])
                    self._rellenar(anillos)
                    Color(*COLOR["sector_activo_borde" if activo else "sector_borde"])
                    for anillo in anillos:
                        Line(points=anillo, close=True, width=dp(1.4) if activo else dp(0.8))
            for s in self.sectores:
                self._etiqueta(s)

    def _a_pantalla(self, anillo):
        puntos = []
        for lng, lat, *_ in anillo:
            x, y = self.proyeccion.a_pantalla(lng, lat)
            puntos += [self.x + x, self.y + y]
        return puntos

    @staticmethod
    def _rellenar(anillos):
        tess = Tesselator()
        for anillo in anillos:
            tess.add_contour(anillo)
        if tess.tesselate(WINDING_ODD, TYPE_POLYGONS):
            for vertices, indices in tess.meshes:
                Mesh(vertices=vertices, indices=indices, mode="triangle_fan")

    def _etiqueta(self, sector):
        # En el centro de la caja de la parte más grande del sector.
        exterior = max((p[0] for p in sector.poligonos), key=len)
        xs, ys = [p[0] for p in exterior], [p[1] for p in exterior]
        x0, y0 = self.proyeccion.a_pantalla(min(xs), min(ys))
        x1, y1 = self.proyeccion.a_pantalla(max(xs), max(ys))
        etiqueta = EtiquetaCore(text=sector.etiqueta, font_size=sp(9), bold=True,
                                color=COLOR["sector_texto"])
        etiqueta.refresh()
        textura = etiqueta.texture
        if textura.width > (x1 - x0) * 1.3:
            return  # polígono muy angosto en pantalla: sin etiqueta para no tapar a los vecinos
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        Color(1, 1, 1, 1)
        Rectangle(texture=textura, size=textura.size,
                  pos=(self.x + x - textura.width / 2, self.y + y - textura.height / 2))

    def on_touch_up(self, touch):
        if not self.collide_point(*touch.pos) or self.proyeccion is None:
            return super().on_touch_up(touch)
        if touch.grab_current is not None:
            return super().on_touch_up(touch)
        lng, lat = self.proyeccion.a_geo(touch.x - self.x, touch.y - self.y)
        self.seleccionado = sector_en(self.sectores, lat, lng)
        return True
