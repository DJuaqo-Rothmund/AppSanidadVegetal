"""GPS del teléfono con plyer; en el computador se simula con una variable de entorno.

    SANIDAD_GPS_FALSO="-39.5467,-72.4663,5"   (lat, lng, precisión en m)

Las lecturas llegan en el hilo principal de Kivy como
al_recibir(lat, lng, precision_m).
"""

import os

from kivy.clock import Clock, mainthread
from kivy.logger import Logger
from kivy.utils import platform


class GPS:
    def __init__(self, al_recibir, al_cambiar_estado=None):
        self.al_recibir = al_recibir
        self.al_cambiar_estado = al_cambiar_estado or (lambda estado: None)
        self.activo = False
        self._evento_falso = None

    def iniciar(self):
        if self.activo:
            return
        if platform == "android":
            try:
                from plyer import gps
                gps.configure(on_location=self._ubicacion, on_status=self._estado)
                gps.start(minTime=1000, minDistance=0)
            except Exception as e:  # noqa: BLE001 - sin GPS la app sigue funcionando
                Logger.warning(f"GPS: no se pudo iniciar ({e})")
                self.al_cambiar_estado("sin GPS")
                return
        else:
            falso = os.environ.get("SANIDAD_GPS_FALSO")
            if not falso:
                self.al_cambiar_estado("sin GPS (computador)")
                return
            lat, lng, *resto = (float(v) for v in falso.split(","))
            precision = resto[0] if resto else 5.0
            self._evento_falso = Clock.schedule_interval(
                lambda dt: self.al_recibir(lat, lng, precision), 1)
            Clock.schedule_once(lambda dt: self.al_recibir(lat, lng, precision), 0)
        self.activo = True
        self.al_cambiar_estado("buscando señal GPS…")

    def detener(self):
        if not self.activo:
            return
        self.activo = False
        if self._evento_falso:
            self._evento_falso.cancel()
            self._evento_falso = None
        if platform == "android":
            try:
                from plyer import gps
                gps.stop()
            except Exception:  # noqa: BLE001
                pass

    @mainthread
    def _ubicacion(self, **kw):
        lat, lng = kw.get("lat"), kw.get("lon")
        if lat is None or lng is None:
            return
        self.al_recibir(float(lat), float(lng), kw.get("accuracy"))

    @mainthread
    def _estado(self, tipo, estado):
        # plyer: tipo "provider-enabled"/"provider-disabled"/"status"
        if tipo == "provider-disabled":
            self.al_cambiar_estado("GPS apagado: actívalo en el teléfono")
        elif tipo == "provider-enabled":
            self.al_cambiar_estado("buscando señal GPS…")
