"""Sesión del monitor: inicio, recuerdo entre aperturas, renovación del token y cierre.

No depende de Kivy, así que se prueba con pytest.
"""

from .db.esquema import TABLAS
from .firebase import ErrorFirebase, Sesion, SinConexion

CLAVE_SESION = "sesion"


class GestorSesion:
    def __init__(self, base, auth):
        self.base = base
        self.auth = auth
        guardada = base.leer_ajuste(CLAVE_SESION)
        self.sesion = Sesion.desde_dict(guardada) if guardada else None

    @property
    def activa(self):
        return self.sesion is not None

    def iniciar(self, email, contrasena):
        self.sesion = self.auth.iniciar_sesion(email, contrasena)
        self._guardar()
        return self.sesion

    def token(self):
        """ID token vigente; lo renueva si está por vencer.

        Sin señal devuelve el token actual aunque esté vencido: la app sigue
        funcionando con la base local y la llamada a Firestore fallará después.
        """
        if self.sesion is None:
            raise ErrorFirebase("UNAUTHENTICATED")
        if self.auth.necesita_renovar(self.sesion):
            try:
                self.sesion = self.auth.renovar(self.sesion)
                self._guardar()
            except SinConexion:
                pass
            except ErrorFirebase:
                self.cerrar()  # token revocado o cuenta desactivada
                raise
        return self.sesion.id_token

    def pendientes_por_subir(self):
        """Cantidad de registros locales sin subir (para avisar antes de cerrar sesión)."""
        return sum(len(self.base.pendientes(t)) for t in TABLAS)

    def cerrar(self):
        self.sesion = None
        self.base.borrar_ajuste(CLAVE_SESION)

    def _guardar(self):
        self.base.guardar_ajuste(CLAVE_SESION, self.sesion.a_dict())
