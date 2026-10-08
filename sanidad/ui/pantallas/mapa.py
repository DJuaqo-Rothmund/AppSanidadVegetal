"""Pantalla de mapa (etapa 2): satélite ESRI o esquema, GPS, sector deducido y mapa sin señal."""

import os
import threading

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField

from ... import prueba_terreno
from ...geo import caja_total, sector_en, teselas
from ...rutas import SECTORES
from ..mapa_satelital import ZOOM_MAX, ZOOM_MIN, CapaSectores, CapaUbicacion, FuenteSatelital
from ..tema import COLOR

ZOOM_DESCARGA = (13, 19)
FONDO_DIALOGO = COLOR["superficie"]
MARGEN_DESCARGA_M = 250


def describir_sector(sector):
    variedad = sector.variedad or " / ".join(sector.propiedades.get("variedades_sector") or [])
    partes = [f"Sector {sector.sector}" if sector.sector else sector.id,
              f"Equipo {sector.equipo}" if sector.equipo else None,
              variedad or "variedad sin dato"]
    return " · ".join(p for p in partes if p)


class PantallaMapa(MDScreen):
    usuario = StringProperty("")
    aviso = StringProperty("")
    satelital = BooleanProperty(True)
    tarjeta_tipo = StringProperty("")
    tarjeta_titulo = StringProperty("")
    tarjeta_detalle = StringProperty("")
    tarjeta_alerta = BooleanProperty(False)
    seleccionado = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._mapa_listo = False
        self._seguir = True  # centrar en la ubicación al recibir el primer GPS

    # --- ciclo de vida ----------------------------------------------------------

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.usuario = app.sesion.sesion.email if app.sesion and app.sesion.activa else ""
        self.aviso = "" if app.sectores else f"Falta el archivo de sectores ({SECTORES.name})."
        self.satelital = app.base.leer_ajuste("mapa_satelital", True)
        if not self._mapa_listo:
            self._armar_mapa(app)
        app.gps_estado.bind(ubicacion=self._al_ubicar, estado=self._actualizar_tarjeta)
        if app.gps_estado.ubicacion is not None:  # llegó antes de entrar a la pantalla
            Clock.schedule_once(lambda dt: self._al_ubicar(None, app.gps_estado.ubicacion), 0.2)
        self._actualizar_tarjeta()

    def on_leave(self, *_):
        App.get_running_app().gps_estado.unbind(ubicacion=self._al_ubicar,
                                                estado=self._actualizar_tarjeta)

    def _armar_mapa(self, app):
        mapa = self.ids.satelite
        mapa.map_source = FuenteSatelital(app.teselas, app.cliente_mapa, cache_dir=app.carpeta_mapa)
        self.capa_sectores = CapaSectores(sectores=app.sectores)
        self.capa_ubicacion = CapaUbicacion()
        mapa.add_layer(self.capa_sectores)
        mapa.add_layer(self.capa_ubicacion)
        mapa.bind(on_toque=lambda _m, lat, lng: self._tocar(lat, lng))
        self.ids.esquema.sectores = app.sectores
        self.ids.esquema.bind(seleccionado=lambda _w, s: setattr(self, "seleccionado", s))
        Clock.schedule_once(lambda dt: self.ver_predio(por_usuario=False), 0)
        self._mapa_listo = True

    # --- acciones de la barra ---------------------------------------------------

    def cambiar_modo(self):
        self.satelital = not self.satelital
        App.get_running_app().base.guardar_ajuste("mapa_satelital", self.satelital)

    def ver_predio(self, por_usuario=True):
        app = App.get_running_app()
        if not app.sectores:
            return
        if por_usuario:
            self._seguir = False
        mapa = self.ids.satelite
        min_lng, min_lat, max_lng, max_lat = caja_total(app.sectores)
        fuente = mapa.map_source
        zoom, escala = ZOOM_MIN, 1.0
        for z in range(ZOOM_MAX, ZOOM_MIN - 1, -1):
            ancho = fuente.get_x(z, max_lng) - fuente.get_x(z, min_lng)
            alto = fuente.get_y(z, max_lat) - fuente.get_y(z, min_lat)
            cabe = min(mapa.width * 0.9 / max(ancho, 1), mapa.height * 0.75 / max(alto, 1))
            if cabe >= 1:
                zoom, escala = z, min(cabe, 1.99)  # entre dos zooms, la escala del mapa ajusta
                break
        mapa.set_zoom_at(zoom, *mapa.center, scale=escala)
        mapa.center_on((min_lat + max_lat) / 2, (min_lng + max_lng) / 2)

    def centrar_en_mi(self):
        u = App.get_running_app().gps_estado.ubicacion
        if u is None:
            self._dialogo("Sin ubicación", "Todavía no hay señal GPS. Sal a cielo abierto y espera unos segundos.")
            return
        self._seguir = True
        mapa = self.ids.satelite
        if mapa.zoom < 17:
            mapa.zoom = 17
        mapa.center_on(u.lat, u.lng)

    def nueva_observacion(self):
        self._dialogo("Próximamente", "El formulario de observación llega en la etapa 3.")

    # --- ubicación y selección --------------------------------------------------

    def _al_ubicar(self, _estado, u):
        if u is None:
            return
        self.capa_ubicacion.ubicacion = (u.lat, u.lng, u.precision_m)
        if self._seguir:
            self._seguir = False
            self.centrar_en_mi()
        self._actualizar_tarjeta()

    def _tocar(self, lat, lng):
        self.seleccionado = sector_en(App.get_running_app().sectores, lat, lng)

    def on_seleccionado(self, _w, sector):
        if self._mapa_listo:
            self.capa_sectores.seleccionado = sector
        self._actualizar_tarjeta()

    def soltar_seleccion(self):
        self.seleccionado = None
        self.ids.esquema.seleccionado = None

    def _actualizar_tarjeta(self, *_):
        app = App.get_running_app()
        s = self.seleccionado
        if s is not None:
            self.tarjeta_tipo = "SECTOR TOCADO"
            self.tarjeta_titulo = describir_sector(s)
            self.tarjeta_detalle = f"{s.ha:g} ha" if s.ha else "superficie sin dato"
            self.tarjeta_alerta = False
            return
        u = app.gps_estado.ubicacion
        self.tarjeta_tipo = "TU UBICACIÓN"
        if u is None:
            self.tarjeta_titulo = "Sin ubicación"
            self.tarjeta_detalle = app.gps_estado.estado or "esperando el GPS…"
            self.tarjeta_alerta = False
            return
        precision = f"±{u.precision_m:.0f} m" if u.precision_m is not None else "precisión desconocida"
        coordenadas = f"{u.lat:.6f}, {u.lng:.6f}"
        if u.sector is not None:
            self.tarjeta_titulo = describir_sector(u.sector)
            borde = f"a {u.distancia_borde_m:.0f} m del borde"
            self.tarjeta_detalle = f"{precision} · {borde} · {coordenadas}"
            self.tarjeta_alerta = u.en_borde
            if u.en_borde:
                self.tarjeta_detalle = f"Cerca del borde: confirma el sector · {precision} · {borde}"
        else:
            self.tarjeta_titulo = "Fuera del predio"
            cerca = (f"a {u.distancia_borde_m:.0f} m de {u.cercano.etiqueta}" if u.cercano else "")
            self.tarjeta_detalle = " · ".join(p for p in (precision, cerca, coordenadas) if p)
            self.tarjeta_alerta = True

    # --- puntos de prueba en terreno -------------------------------------------

    def anotar_punto(self):
        app = App.get_running_app()
        u = app.gps_estado.ubicacion
        if u is None:
            self._dialogo("Sin ubicación", "Espera a tener señal GPS para anotar el punto.")
            return
        campo = MDTextField(hint_text="Nota (por ejemplo, qué dice el plano)", mode="rectangle")
        caja = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(8))
        caja.add_widget(MDLabel(text=f"{self.tarjeta_titulo}\n{self.tarjeta_detalle}",
                                adaptive_height=True, font_style="Body2"))
        caja.add_widget(campo)
        dialogo = None

        def guardar(*_):
            fila = prueba_terreno.anotar(app.base, u, campo.text.strip())
            dialogo.dismiss()
            self._dialogo("Punto anotado", f"Punto {fila['n']} guardado. "
                          f"Llevas {fila['n']} de 10 para la prueba de la etapa 2.")

        dialogo = MDDialog(
            title="Anotar punto de prueba", type="custom", content_cls=caja, md_bg_color=FONDO_DIALOGO,
            buttons=[MDFlatButton(text="CANCELAR", on_release=lambda *_: dialogo.dismiss()),
                     MDFlatButton(text="GUARDAR", on_release=guardar)])
        dialogo.open()

    def ver_puntos(self):
        app = App.get_running_app()
        puntos = prueba_terreno.listar(app.base)
        if not puntos:
            self._dialogo("Puntos de prueba", "Todavía no hay puntos anotados.")
            return
        lineas = []
        for p in puntos:
            donde = (f"S{p['sector']} · E{p['equipo']}" if p["sector"] else f"fuera ({p['fuera_cerca_de']})")
            borde = " ⚠ borde" if p["en_borde"] else ""
            lineas.append(f"{p['n']}. {donde} · ±{p['precision_m']} m{borde} {p['nota']}".rstrip())
        prueba_terreno.exportar_csv(app.base, os.path.join(app.user_data_dir, "puntos_prueba.csv"))
        self._dialogo("Puntos de prueba", "\n".join(lineas))

    # --- descarga del mapa sin señal -------------------------------------------

    def descargar_mapa(self):
        app = App.get_running_app()
        if not app.sectores:
            return
        cajas = [s.caja() for s in app.sectores]
        plan = teselas.planificar(app.teselas, cajas, *ZOOM_DESCARGA, margen_m=MARGEN_DESCARGA_M)
        guardado = app.teselas.resumen()
        texto = MDLabel(adaptive_height=True, font_style="Body2", text=(
            f"Zoom {plan.zoom_min} a {plan.zoom_max}, sectores más {MARGEN_DESCARGA_M} m.\n"
            f"Ya guardadas: {plan.ya_guardadas} teselas ({guardado['bytes'] / 1_048_576:.1f} MB).\n"
            f"Faltan: {len(plan.pendientes)} teselas (~{plan.megas_estimados:.0f} MB).\n\n"
            "Hazlo con wifi o buena señal. Imágenes © Esri."))
        barra = MDProgressBar(value=0, max=100, size_hint_y=None, height=dp(6))
        caja = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(12))
        caja.add_widget(texto)
        caja.add_widget(barra)
        cancelar = threading.Event()
        estado = {"corriendo": False}
        boton_accion = MDFlatButton(text="DESCARGAR" if plan.pendientes else "LISTO")
        boton_cerrar = MDFlatButton(text="CERRAR")
        dialogo = MDDialog(title="Mapa sin señal", type="custom", content_cls=caja, md_bg_color=FONDO_DIALOGO,
                           auto_dismiss=False, buttons=[boton_cerrar, boton_accion])

        @mainthread
        def avanzar(av):
            barra.value = av.fraccion * 100
            texto.text = (f"{'Guardadas' if av.terminado else 'Descargando…'} {av.listas} de {av.total} teselas"
                          f" ({av.bytes / 1_048_576:.1f} MB)" + (f", {av.fallidas} con error" if av.fallidas else ""))
            if av.terminado:
                estado["corriendo"] = False
                boton_accion.text = "LISTO"
                boton_cerrar.text = "CERRAR"
                if av.motivo_corte:
                    texto.text += f"\n\n{av.motivo_corte} Vuelve a intentarlo con señal: sigue donde quedó."
                elif av.cancelado:
                    texto.text += "\n\nDescarga detenida. Puedes seguirla después."
                else:
                    texto.text += "\n\nListo: el mapa del predio queda disponible sin señal."
                self.ids.satelite.trigger_update(True)

        def accion(*_):
            if boton_accion.text != "DESCARGAR":
                dialogo.dismiss()
                return
            estado["corriendo"] = True
            boton_accion.text = "…"
            boton_cerrar.text = "DETENER"
            cliente = teselas.ClienteTeselas()
            threading.Thread(target=teselas.descargar, daemon=True, kwargs=dict(
                plan=plan, almacen=app.teselas, obtener=cliente.obtener,
                al_avanzar=avanzar, cancelar=cancelar)).start()

        def cerrar(*_):
            if estado["corriendo"]:
                cancelar.set()
            else:
                dialogo.dismiss()

        boton_accion.bind(on_release=accion)
        boton_cerrar.bind(on_release=cerrar)
        dialogo.open()

    # --- sesión -------------------------------------------------------------------

    def cerrar_sesion(self):
        app = App.get_running_app()
        if app.sesion is None:
            app.ir_a("login", direccion="right")
            return
        pendientes = app.sesion.pendientes_por_subir()
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
        dialogo = None

        def cerrar(*_):
            dialogo.dismiss()

        def aceptar(*_):
            dialogo.dismiss()
            confirmar()

        if confirmar:
            botones = [MDFlatButton(text="CANCELAR", on_release=cerrar),
                       MDFlatButton(text="CERRAR SESIÓN", on_release=aceptar)]
        else:
            botones = [MDFlatButton(text="ENTENDIDO", on_release=cerrar)]
        dialogo = MDDialog(title=titulo, text=texto, buttons=botones, md_bg_color=FONDO_DIALOGO)
        dialogo.open()
