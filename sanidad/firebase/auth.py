"""Firebase Authentication por API REST: correo y contraseña, y renovación del token."""

import time
from dataclasses import asdict, dataclass

import requests

from .errores import ErrorFirebase, SinConexion, revisar_respuesta

URL_INICIO = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
URL_RENOVAR = "https://securetoken.googleapis.com/v1/token"
MARGEN_RENOVACION_S = 120
TIEMPO_ESPERA_S = 20


@dataclass
class Sesion:
    uid: str
    email: str
    id_token: str
    refresh_token: str
    expira_en: float  # segundos desde la época

    def a_dict(self):
        return asdict(self)

    @classmethod
    def desde_dict(cls, d):
        return cls(**d)


class ClienteAuth:
    def __init__(self, api_key, http=None, reloj=time.time):
        self.api_key = api_key
        self.http = http or requests.Session()
        self.reloj = reloj

    def _post(self, url, **kwargs):
        try:
            r = self.http.post(url, params={"key": self.api_key}, timeout=TIEMPO_ESPERA_S, **kwargs)
        except requests.RequestException as e:
            raise SinConexion() from e
        return revisar_respuesta(r)

    def iniciar_sesion(self, email, contrasena):
        email = (email or "").strip()
        if not email or not contrasena:
            raise ErrorFirebase("DATOS_INCOMPLETOS")
        d = self._post(URL_INICIO, json={
            "email": email, "password": contrasena, "returnSecureToken": True,
        })
        return Sesion(
            uid=d["localId"], email=d.get("email", email), id_token=d["idToken"],
            refresh_token=d["refreshToken"], expira_en=self.reloj() + int(d["expiresIn"]),
        )

    def renovar(self, sesion):
        d = self._post(URL_RENOVAR, data={
            "grant_type": "refresh_token", "refresh_token": sesion.refresh_token,
        })
        return Sesion(
            uid=d["user_id"], email=sesion.email, id_token=d["id_token"],
            refresh_token=d["refresh_token"], expira_en=self.reloj() + int(d["expires_in"]),
        )

    def necesita_renovar(self, sesion):
        return self.reloj() >= sesion.expira_en - MARGEN_RENOVACION_S
