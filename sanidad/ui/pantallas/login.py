"""Pantalla de inicio de sesión con correo y contraseña."""

import threading

from kivy.app import App
from kivy.clock import mainthread
from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.screen import MDScreen

from ...firebase import ErrorFirebase


class PantallaLogin(MDScreen):
    error = StringProperty("")
    ocupado = BooleanProperty(False)
    sin_firebase = BooleanProperty(False)

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.sin_firebase = app.sesion is None
        self.error = ("Falta configurar Firebase: puedes probar la app sin cuenta. "
                      "Lo que registres queda en este teléfono.") if self.sin_firebase else ""

    def entrar_sin_cuenta(self):
        """Modo de prueba mientras no hay Firebase: todo queda en el teléfono."""
        App.get_running_app().ir_a("mapa")

    def entrar(self):
        app = App.get_running_app()
        if app.sesion is None:
            self.error = app.error_config or "Falta la configuración de Firebase."
            return
        email = self.ids.email.text
        contrasena = self.ids.contrasena.text
        self.error = ""
        self.ocupado = True
        threading.Thread(target=self._entrar, args=(app.sesion, email, contrasena), daemon=True).start()

    def _entrar(self, sesion, email, contrasena):
        try:
            sesion.iniciar(email, contrasena)
        except ErrorFirebase as e:
            self._terminar(e.mensaje)
        else:
            self._terminar(None)

    @mainthread
    def _terminar(self, error):
        self.ocupado = False
        if error:
            self.error = error
            return
        self.ids.contrasena.text = ""
        App.get_running_app().ir_a("mapa")
