"""Aplicación Kivy: arma los servicios (base, Firebase, catálogo, mapa, GPS) y las pantallas."""

import os
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.event import EventDispatcher
from kivy.lang import Builder
from kivy.properties import ObjectProperty, StringProperty
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager

from .. import __version__, rutas
from ..catalogo import cargar_catalogo
from ..config import RAIZ_PROYECTO, ConfiguracionFaltante, cargar_config
from ..db import BaseLocal
from ..firebase import ClienteAuth, ClienteFirestore
from ..geo import cargar_sectores, teselas, ubicar
from ..gps import GPS
from ..sesion import GestorSesion
from . import tema
from .mapa_esquematico import MapaEsquematico  # noqa: F401  (registro para el .kv)
from .mapa_satelital import MapaSatelital  # noqa: F401  (registro para el .kv)
from .pantallas.login import PantallaLogin
from .pantallas.mapa import PantallaMapa

KV = Path(__file__).parent / "kv"


tema.instalar_paleta()  # antes de crear la app, como en PhenoRubus


class EstadoGPS(EventDispatcher):
    """Última ubicación conocida (geo.Ubicacion) y estado del GPS, para las pantallas."""
    ubicacion = ObjectProperty(None, allownone=True)
    estado = StringProperty("")


class SanidadApp(MDApp):
    title = "Sanidad · El Amanecer"
    version = __version__

    def build(self):
        if platform not in ("android", "ios"):
            Window.size = (390, 844)
        tema.aplicar_tema(self.theme_cls)
        Window.clearcolor = tema.COLOR["fondo"]
        self.colores = tema.COLOR
        for archivo in sorted(KV.glob("*.kv")):
            Builder.load_file(str(archivo))

        self._iniciar_servicios()

        self.pantallas = MDScreenManager()
        self.pantallas.add_widget(PantallaLogin(name="login"))
        self.pantallas.add_widget(PantallaMapa(name="mapa"))
        self.pantallas.current = "mapa" if self.sesion and self.sesion.activa else "login"
        return self.pantallas

    def _iniciar_servicios(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        self.base = BaseLocal(os.path.join(self.user_data_dir, "sanidad.sqlite3"))
        self.catalogo = cargar_catalogo(rutas.CATALOGO)
        self.sectores = cargar_sectores(rutas.SECTORES) if rutas.SECTORES.is_file() else []

        # Mapa satelital: teselas en MBTiles dentro de los datos de la app
        carpeta_mapa = os.path.join(self.user_data_dir, "mapa")
        os.makedirs(carpeta_mapa, exist_ok=True)
        self.carpeta_mapa = carpeta_mapa
        self.teselas = teselas.AlmacenTeselas(os.path.join(carpeta_mapa, "esri_world_imagery.mbtiles"))
        self.cliente_mapa = teselas.ClienteTeselas(tiempo_espera_s=6, reintentos=0)

        self.gps_estado = EstadoGPS()
        self.gps = GPS(self._al_recibir_gps, lambda e: setattr(self.gps_estado, "estado", e))

        self.error_config = None
        self.config_firebase = None
        self.sesion = None
        self.firestore = None
        try:
            self.config_firebase = cargar_config([RAIZ_PROYECTO, self.user_data_dir])
        except ConfiguracionFaltante as e:
            self.error_config = str(e)
            return
        auth = ClienteAuth(self.config_firebase["apiKey"])
        self.sesion = GestorSesion(self.base, auth)
        self.firestore = ClienteFirestore(self.config_firebase["projectId"], token=self.sesion.token)

    def on_start(self):
        if platform == "android":
            from android.permissions import Permission, request_permissions
            request_permissions([
                Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION,
                Permission.CAMERA,
            ], self._permisos)
        else:
            self.gps.iniciar()

    def _permisos(self, permisos, concedidos):
        if any(p.endswith("ACCESS_FINE_LOCATION") and ok for p, ok in zip(permisos, concedidos)):
            Clock.schedule_once(lambda dt: self.gps.iniciar(), 0)
        else:
            Clock.schedule_once(lambda dt: setattr(
                self.gps_estado, "estado", "sin permiso de ubicación"), 0)

    def _al_recibir_gps(self, lat, lng, precision_m):
        self.gps_estado.ubicacion = ubicar(self.sectores, lat, lng, precision_m)
        self.gps_estado.estado = "GPS activo"

    def on_pause(self):
        self.gps.detener()
        return True

    def on_resume(self):
        self.gps.iniciar()

    def ir_a(self, pantalla, direccion="left"):
        self.pantallas.transition.direction = direccion
        self.pantallas.current = pantalla

    def on_stop(self):
        self.gps.detener()
        self.teselas.cerrar()
        self.base.cerrar()
