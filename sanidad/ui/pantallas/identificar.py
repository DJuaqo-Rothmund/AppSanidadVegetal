"""Pestaña Identificar: foto → la IA sugiere especies → el monitor confirma y la IA aprende."""

import os
import threading

from kivy.app import App
from kivy.clock import mainthread
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList, TwoLineListItem
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField

from ... import rutas
from ...ia.servicio import CatalogoEspecies
from ..tema import COLOR

NOMBRES_GRUPO = {"maleza": "Malezas", "enfermedad": "Enfermedades", "plaga": "Plagas"}
CAMPOS_FICHA = [("descripcion", "Descripción"), ("ciclo_de_vida", "Ciclo de vida"),
                ("reproduccion", "Reproducción"), ("habitat", "Hábitat"), ("origen", "Origen")]


def foto_de_libro(ficha):
    fotos = (ficha or {}).get("fotos") or []
    ruta = rutas.FOTOS_ESPECIES / fotos[0] if fotos else None
    return str(ruta) if ruta and ruta.is_file() else ""


class TarjetaSugerencia(MDCard):
    especie_id = StringProperty("")
    nombre = StringProperty("")
    cientifico = StringProperty("")
    detalle = StringProperty("")
    foto = StringProperty("")
    confianza = NumericProperty(0)


class PantallaIdentificar(MDScreen):
    grupo = StringProperty("maleza")
    foto = StringProperty("")
    estado = StringProperty("Toma o elige una foto de la planta.")
    ocupado = BooleanProperty(False)
    resumen = StringProperty("")
    sugerencias = ListProperty([])

    # --- navegación -----------------------------------------------------------------

    def on_pre_enter(self, *_):
        self._actualizar_resumen()

    def volver(self):
        App.get_running_app().ir_a("mapa", direccion="right")

    def elegir_grupo(self, grupo):
        self.grupo = grupo
        if self.foto:
            self.analizar()

    def _actualizar_resumen(self):
        app = App.get_running_app()
        especies = len(app.especies.del_grupo(self.grupo))
        if not especies:
            self.resumen = f"No hay especies de {NOMBRES_GRUPO[self.grupo].lower()} en el catálogo."
            return

        def calcular():
            r = app.identificacion.resumen()
            self._poner_resumen(f"{especies} especies de {NOMBRES_GRUPO[self.grupo].lower()} · "
                                f"referencias: {r['fotos_libro']} fotos del libro, "
                                f"{r['fotos_terreno']} de terreno")

        threading.Thread(target=calcular, daemon=True).start()

    @mainthread
    def _poner_resumen(self, texto):
        self.resumen = texto

    # --- foto -------------------------------------------------------------------------

    def tomar_foto(self):
        App.get_running_app().medios.tomar_foto(self._foto_lista)

    def elegir_de_galeria(self):
        App.get_running_app().medios.elegir_de_galeria(self._foto_lista)

    def _foto_lista(self, ruta):
        if not ruta:
            self.estado = "No se recibió la foto."
            return
        self.foto = ruta
        self.analizar()

    def analizar(self):
        if not self.foto or self.ocupado:
            return
        app = App.get_running_app()
        self.ocupado = True
        self.estado = "Analizando la foto…"
        self.ids.resultados.clear_widgets()
        foto, grupo = self.foto, self.grupo

        def trabajo():
            try:
                resultado = app.identificacion.identificar(foto, grupo=grupo)
                self._mostrar(resultado, None)
            except Exception as e:  # noqa: BLE001 - mostrar el error, no cerrar la app
                self._mostrar([], str(e))

        threading.Thread(target=trabajo, daemon=True).start()

    @mainthread
    def _mostrar(self, resultado, error):
        self.ocupado = False
        caja = self.ids.resultados
        caja.clear_widgets()
        if error:
            self.estado = f"No se pudo analizar la foto: {error}"
            return
        if not resultado:
            self.estado = ("La IA todavía no tiene referencias de este grupo. "
                           "Elige la especie con «Otra especie…» para enseñarle.")
            return
        self.estado = "¿Es alguna de estas? Confirma la correcta para que la IA aprenda."
        for s, ficha in resultado:
            caja.add_widget(TarjetaSugerencia(
                especie_id=s.especie_id,
                nombre=CatalogoEspecies.nombre(ficha),
                cientifico=ficha.get("cientifico") or "",
                detalle=" · ".join(p for p in ((ficha.get("familia") or "").capitalize(),
                                               f"{s.referencias} fotos de referencia") if p),
                foto=foto_de_libro(ficha),
                confianza=s.confianza))

    # --- confirmar y aprender -----------------------------------------------------------

    def confirmar(self, especie_id):
        app = App.get_running_app()
        if not self.foto:
            return
        ficha = app.especies.ficha(especie_id)
        uid = app.sesion.sesion.uid if app.sesion and app.sesion.activa else None
        foto = self.foto
        self.ocupado = True
        self.estado = "Guardando la referencia…"

        def trabajo():
            try:
                app.identificacion.confirmar(foto, especie_id, uid=uid)
                n = len(app.identificacion.referencias_de(especie_id))
                self._confirmado(f"Listo: la foto quedó como referencia de "
                                 f"{CatalogoEspecies.nombre(ficha)} ({n} de terreno). "
                                 "La IA ya la usa para sugerir.")
            except Exception as e:  # noqa: BLE001
                self._confirmado(f"No se pudo guardar: {e}")

        threading.Thread(target=trabajo, daemon=True).start()

    @mainthread
    def _confirmado(self, texto):
        self.ocupado = False
        self.estado = texto
        self.ids.resultados.clear_widgets()
        self._actualizar_resumen()

    def otra_especie(self):
        app = App.get_running_app()
        campo = MDTextField(hint_text="Busca por nombre común, científico o familia", mode="rectangle")
        lista = MDList()
        desplazable = ScrollView(size_hint_y=None, height=dp(320))
        desplazable.add_widget(lista)
        caja = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(8))
        caja.add_widget(campo)
        caja.add_widget(desplazable)
        dialogo = None

        def elegir(especie_id):
            dialogo.dismiss()
            if self.foto:
                self.confirmar(especie_id)
            else:
                self.ver_ficha(especie_id)

        def filtrar(*_):
            lista.clear_widgets()
            for e in app.especies.buscar(campo.text, grupo=self.grupo):
                lista.add_widget(TwoLineListItem(
                    text=CatalogoEspecies.nombre(e), secondary_text=e.get("cientifico") or "",
                    on_release=lambda _w, i=e["id"]: elegir(i)))

        campo.bind(text=filtrar)
        filtrar()
        dialogo = MDDialog(title="Elegir especie", type="custom", content_cls=caja,
                           md_bg_color=COLOR["superficie"],
                           buttons=[MDFlatButton(text="CANCELAR", on_release=lambda *_: dialogo.dismiss())])
        dialogo.open()

    def ver_ficha(self, especie_id):
        app = App.get_running_app()
        ficha = app.especies.ficha(especie_id)
        if not ficha:
            return
        caja = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(8), padding=(0, 0, dp(8), 0))
        fotos = MDBoxLayout(size_hint_y=None, height=dp(150), spacing=dp(6))
        for nombre in ficha.get("fotos") or []:
            ruta = rutas.FOTOS_ESPECIES / nombre
            if ruta.is_file():
                fotos.add_widget(Image(source=str(ruta), fit_mode="cover"))
        if fotos.children:
            caja.add_widget(fotos)
        texto = [f"[i]{ficha.get('cientifico', '')}[/i]"]
        if ficha.get("familia"):
            texto.append(ficha["familia"].capitalize())
        comunes = ficha.get("nombres_comunes") or []
        if len(comunes) > 1:
            texto.append("También: " + ", ".join(n.capitalize() for n in comunes[1:]))
        for clave, titulo in CAMPOS_FICHA:
            valor = ficha.get(clave)
            if isinstance(valor, dict):
                valor = "\n".join(f"{k}: {v}" for k, v in valor.items())
            if valor:
                texto.append(f"[b]{titulo}[/b]\n{valor}")
        refs = len(app.identificacion.referencias_de(especie_id))
        texto.append(f"[color=#6E7E75]Referencias de terreno: {refs}. "
                     "Fuente: Espinoza (1996), Malezas presentes en Chile, INIA (texto por OCR).[/color]")
        caja.add_widget(MDLabel(text="\n\n".join(texto), markup=True, adaptive_height=True, font_style="Body2"))
        desplazable = ScrollView(size_hint_y=None, height=dp(440))
        desplazable.add_widget(caja)
        dialogo = None
        dialogo = MDDialog(title=CatalogoEspecies.nombre(ficha), type="custom", content_cls=desplazable,
                           md_bg_color=COLOR["superficie"],
                           buttons=[MDFlatButton(text="CERRAR", on_release=lambda *_: dialogo.dismiss())])
        dialogo.open()
