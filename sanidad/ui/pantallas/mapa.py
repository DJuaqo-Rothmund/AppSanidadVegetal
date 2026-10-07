"""Pantalla de mapa provisoria (etapa 1): sectores esquemáticos y sesión."""

from kivy.app import App
from kivy.properties import StringProperty
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.screen import MDScreen

from ...rutas import SECTORES


class PantallaMapa(MDScreen):
    usuario = StringProperty("")
    aviso = StringProperty("")
    detalle = StringProperty("")

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.usuario = app.sesion.sesion.email if app.sesion and app.sesion.activa else ""
        self.ids.mapa.sectores = app.sectores
        if not app.sectores:
            self.aviso = (f"Falta el archivo de sectores ({SECTORES.name}). "
                          "El mapa del predio llega en la etapa 2.")
        else:
            self.aviso = ""
        n = len(app.catalogo.organismos)
        self.detalle = f"Catálogo {app.catalogo.id}: {n} organismos · {len(app.sectores)} polígonos"

    def on_sector(self, sector):
        if sector is None:
            self.ids.tarjeta.opacity = 0
            return
        partes = [f"Sector {sector.sector}" if sector.sector else sector.id,
                  f"Equipo {sector.equipo}" if sector.equipo else None,
                  sector.variedad or "variedad sin dato"]
        self.ids.tarjeta_titulo.text = " · ".join(p for p in partes if p)
        self.ids.tarjeta_detalle.text = f"{sector.ha:g} ha" if sector.ha else "superficie sin dato"
        self.ids.tarjeta.opacity = 1

    def nueva_observacion(self):
        self._dialogo("Próximamente", "El formulario de observación llega en la etapa 3.")

    def cerrar_sesion(self):
        app = App.get_running_app()
        pendientes = app.sesion.pendientes_por_subir() if app.sesion else 0
        texto = "¿Cerrar la sesión en este teléfono?"
        if pendientes:
            texto = (f"Quedan {pendientes} registros sin subir. Si cierras la sesión "
                     "se subirán cuando vuelvas a entrar. ¿Cerrar igual?")
        self._dialogo("Cerrar sesión", texto, confirmar=self._cerrar)

    def _cerrar(self):
        app = App.get_running_app()
        app.sesion.cerrar()
        app.ir_a("login", direccion="right")

    def _dialogo(self, titulo, texto, confirmar=None):
        botones = []
        dialogo = None

        def cerrar(*_):
            dialogo.dismiss()

        def aceptar(*_):
            dialogo.dismiss()
            confirmar()

        if confirmar:
            botones.append(MDFlatButton(text="CANCELAR", on_release=cerrar))
            botones.append(MDFlatButton(text="CERRAR SESIÓN", on_release=aceptar))
        else:
            botones.append(MDFlatButton(text="ENTENDIDO", on_release=cerrar))
        dialogo = MDDialog(title=titulo, text=texto, buttons=botones)
        dialogo.open()
