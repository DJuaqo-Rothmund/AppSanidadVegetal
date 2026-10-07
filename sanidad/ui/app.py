"""Aplicación Kivy: arma los servicios (base, Firebase, catálogo) y las pantallas."""

import os
from pathlib import Path

from kivy.core.window import Window
from kivy.lang import Builder
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager

from .. import __version__, rutas
from ..catalogo import cargar_catalogo
from ..config import RAIZ_PROYECTO, ConfiguracionFaltante, cargar_config
from ..db import BaseLocal
from ..firebase import ClienteAuth, ClienteFirestore
from ..geo import cargar_sectores
from ..sesion import GestorSesion
from . import tema
from .mapa_esquematico import MapaEsquematico  # noqa: F401  (registro para el .kv)
from .pantallas.login import PantallaLogin
from .pantallas.mapa import PantallaMapa

KV = Path(__file__).parent / "kv"


class SanidadApp(MDApp):
    title = "Sanidad · El Amanecer"
    version = __version__

    def build(self):
        if platform not in ("android", "ios"):
            Window.size = (390, 844)
        tema.registrar_fuentes()
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
            ])

    def ir_a(self, pantalla, direccion="left"):
        self.pantallas.transition.direction = direccion
        self.pantallas.current = pantalla

    def on_stop(self):
        self.base.cerrar()
